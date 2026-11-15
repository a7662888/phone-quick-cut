# -*- coding: utf-8 -*-
"""Read-only runtime doctor; --install installs Python packages in an isolated venv."""
import argparse
import importlib.metadata
import importlib.util
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
MIN_PYTHON, MAX_PYTHON = (3, 10), (3, 14)
REQUIRED_FILTERS = ("subtitles", "loudnorm", "scale", "overlay", "zoompan", "sidechaincompress", "tpad")
MODULES = {"edge-tts": "edge_tts", "faster-whisper": "faster_whisper", "scenedetect": "scenedetect",
           "opencv-python": "cv2", "pillow": "PIL", "pillow-heif": "pillow_heif", "numpy": "numpy", "requests": "requests"}


def invoke(command, timeout=30, **kwargs):
    return subprocess.run([str(x) for x in command], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout, **kwargs)


def install_ffmpeg_hint():
    return {"Windows": "winget install -e --id Gyan.FFmpeg (then reopen the terminal)",
            "Darwin": 'brew install ffmpeg-full\nexport PATH="$(brew --prefix ffmpeg-full)/bin:$PATH"'}.get(platform.system(), "sudo apt-get update && sudo apt-get install -y ffmpeg fonts-noto-cjk")


def version_tuple(value):
    """Compare numeric release bounds from requirements.txt without importing packaging."""
    m = re.match(r"\d+(?:\.\d+)*", value)
    if not m:
        raise ValueError("Unrecognized release")
    parts = tuple(int(x) for x in m.group().split("."))
    return parts + (0,) * max(0, 4 - len(parts))


def requirements():
    for line in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        m = re.fullmatch(r"([A-Za-z0-9_-]+)(?:\[[^]]+\])?((?:(?:>=|<)[0-9.]+)(?:,(?:>=|<)[0-9.]+)*)", line)
        if not m:
            raise ValueError(f"Unsupported dependency constraint: {line}")
        yield m.group(1), re.findall(r"(>=|<)([0-9.]+)", m.group(2))


def check_modules():
    checks = []
    for package, limits in requirements():
        module = MODULES.get(package.lower(), package.replace("-", "_"))
        ok = found = False
        try:
            installed = importlib.metadata.version(package)
            release = version_tuple(installed)
            ok = all(release >= version_tuple(v) if op == ">=" else release < version_tuple(v) for op, v in limits)
            found = importlib.util.find_spec(module) is not None
            detail = installed if ok and found else f"installed {installed}; needs " + ",".join(op + v for op, v in limits)
            if ok and found:
                probe = invoke([sys.executable, "-B", "-c", f"import {module}"], timeout=30,
                               env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
                ok = probe.returncode == 0
                if not ok:
                    detail = "Installed, but import failed (binary/runtime dependency); reinstall in the venv."
        except (importlib.metadata.PackageNotFoundError, ImportError, ValueError, OSError, subprocess.TimeoutExpired):
            ok, detail = False, "Missing or unusable; run setup_env.py --install."
        checks.append({"name": package, "ok": bool(ok and found), "required": True, "detail": detail})
    return checks


def check_ffmpeg():
    ff, fp = shutil.which("ffmpeg"), shutil.which("ffprobe")
    checks = [{"name": "ffmpeg", "ok": bool(ff), "required": True, "detail": ff or install_ffmpeg_hint()},
              {"name": "ffprobe", "ok": bool(fp), "required": True, "detail": fp or install_ffmpeg_hint()}]
    if not (ff and fp):
        return checks
    for name, flag, required in [("filters", "-filters", REQUIRED_FILTERS), ("encoders", "-encoders", ("libx264", "aac"))]:
        try:
            r = invoke([ff, "-hide_banner", flag])
            text = r.stdout + r.stderr
            missing = [item for item in required if not re.search(r"\b" + re.escape(item) + r"\b", text)]
            detail = "Missing: " + ", ".join(missing) if missing else "Required capabilities present"
            if missing and platform.system() == "Darwin":
                detail += "; use ffmpeg-full and prepend its bin directory to PATH. " + install_ffmpeg_hint()
            checks.append({"name": "ffmpeg_" + name, "ok": r.returncode == 0 and not missing,
                           "required": True, "detail": detail})
        except (OSError, subprocess.TimeoutExpired) as exc:
            checks.append({"name": "ffmpeg_" + name, "ok": False, "required": True, "detail": type(exc).__name__})
    try:
        r = invoke([fp, "-version"])
        checks.append({"name": "ffprobe_execution", "ok": r.returncode == 0, "required": True, "detail": "Executable starts"})
    except (OSError, subprocess.TimeoutExpired) as exc:
        checks.append({"name": "ffprobe_execution", "ok": False, "required": True, "detail": type(exc).__name__})
    return checks


def check_font():
    from pqc_common import find_font_path, font_family
    try:
        font = find_font_path()
        if font is None:
            return {"name": "cjk_subtitles", "ok": False, "required": True,
                    "detail": "Install Noto Sans TC/CJK TC, or set PQC_FONT_FILE to a CJK .ttf/.otf/.ttc file."}
        if not shutil.which("ffmpeg"):
            return {"name": "cjk_subtitles", "ok": False, "required": True, "detail": "FFmpeg is required for the font probe."}
        with tempfile.TemporaryDirectory(prefix="pqc-font-") as tmp:
            work = Path(tmp)
            shutil.copy2(font, work / ("probe" + font.suffix))
            ass = ("[Script Info]\nScriptType: v4.00+\nPlayResX: 640\nPlayResY: 360\n"
                   "[V4+ Styles]\nFormat: Name,Fontname,Fontsize,PrimaryColour,OutlineColour,BorderStyle,Outline,Alignment,MarginL,MarginR,MarginV,Encoding\n"
                   f"Style: Default,{font_family()},40,&H00000000,&H00000000,1,0,2,10,10,30,1\n"
                   "[Events]\nFormat: Layer,Start,End,Style,Text\nDialogue: 0,0:00:00.00,0:00:01.00,Default,手機快剪中文字型測試\n")
            (work / "probe.ass").write_text(ass, encoding="utf-8")
            r = invoke(["ffmpeg", "-hide_banner", "-loglevel", "verbose", "-f", "lavfi", "-i", "color=white:s=640x360:d=0.1",
                        "-vf", "subtitles=probe.ass:fontsdir=.", "-frames:v", "1", "-y", "probe.png"], cwd=work)
            ok = r.returncode == 0 and (work / "probe.png").exists() and not re.search(r"Glyph .*not found|failed to find.*glyph", r.stderr, re.I)
            if ok:
                from PIL import Image
                lo, _ = Image.open(work / "probe.png").convert("L").getextrema()
                ok = lo < 100
            return {"name": "cjk_subtitles", "ok": ok, "required": True,
                    "detail": f"Chinese subtitle render {'passed' if ok else 'failed'}: {font}"}
    except Exception as exc:
        return {"name": "cjk_subtitles", "ok": False, "required": True, "detail": f"Font probe failed: {type(exc).__name__}: {exc}"}


def check_agent(agent):
    from pqc_common import agent_command
    try:
        command = agent_command(agent)
    except RuntimeError:
        return {"name": agent + "_auth", "ok": False, "required": True, "detail": f"Install {agent} CLI and sign in, or use --mode manual/template."}
    command += ["login", "status"] if agent == "codex" else ["auth", "status", "--json"]
    try:
        r = invoke(command, timeout=20)
        ok = r.returncode == 0
        if agent == "claude" and ok:
            info = json.loads(r.stdout)
            ok = info.get("loggedIn") is True
        return {"name": agent + "_auth", "ok": ok, "required": True,
                "detail": "CLI reports authenticated; model access/quota was not tested." if ok else "Not authenticated or status command unsupported; sign in and retry."}
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return {"name": agent + "_auth", "ok": False, "required": True, "detail": "Unable to verify CLI authentication (no model call was made)."}


def doctor(agent=None):
    from pqc_common import INBOX, OUTBOX, VIDEO_ROOT, _detect_onedrive_root
    checks = [{"name": "python", "ok": MIN_PYTHON <= sys.version_info[:2] < MAX_PYTHON, "required": True,
               "detail": f"Python {platform.python_version()}; supported: 3.10 through 3.13"}]
    checks.extend(check_modules())
    checks.extend(check_ffmpeg())
    checks.append(check_font())
    if agent:
        checks.append(check_agent(agent))
    else:
        checks.append({"name": "agent", "ok": None, "required": False, "detail": "Not checked. Use --agent codex/claude for CLI auth, or --mode manual/template without a CLI."})
    configured = bool(os.environ.get("PQC_INBOX"))
    onedrive = _detect_onedrive_root() != Path.home() / "Videos"
    checks.append({"name": "phone_sync", "ok": None, "required": False,
                   "detail": "Custom inbox: confirm cloud sync and offline availability yourself." if configured else
                   ("OneDrive detected; ensure the inbox is always available locally. Sync was not tested." if onedrive else "No OneDrive detected. Local Videos fallback works locally, but does not sync phone uploads.")})
    checks.append({"name": "network_services", "ok": None, "required": False,
                   "detail": "Edge-TTS, Whisper model downloads and optional paid APIs were not called; they need network access when used."})
    return {"ok": all(c["ok"] for c in checks if c["required"]), "python": sys.executable,
            "paths": {"PQC_INBOX": str(INBOX), "PQC_OUTBOX": str(OUTBOX), "PQC_VIDEO": str(VIDEO_ROOT)}, "checks": checks}


def install_in_venv(path, agent=None, as_json=False):
    if not MIN_PYTHON <= sys.version_info[:2] < MAX_PYTHON:
        raise RuntimeError("Use Python 3.10 through 3.13 to create the virtual environment.")
    target = Path(path).expanduser().resolve()
    python = target / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not python.exists():
        if target.exists() and any(target.iterdir()):
            raise RuntimeError(f"Refusing to create a venv in a nonempty directory: {target}")
        subprocess.run([sys.executable, "-m", "venv", str(target)], check=True)
    probe = invoke([python, "-c", "import sys; print(int(sys.prefix != sys.base_prefix))"])
    if probe.returncode or probe.stdout.strip() != "1":
        raise RuntimeError(f"Not an isolated Python virtual environment: {target}")
    subprocess.run([str(python), "-m", "pip", "install", "-r", str(ROOT / "requirements.txt")], check=True)
    from pqc_common import INBOX, OUTBOX, VIDEO_ROOT
    for folder in (INBOX, OUTBOX, VIDEO_ROOT):
        folder.mkdir(parents=True, exist_ok=True)
    command = [str(python), "-X", "utf8", str(Path(__file__).resolve())]
    if agent:
        command.extend(["--agent", agent])
    if as_json:
        command.append("--json")
    return subprocess.run(command).returncode


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--install", action="store_true", help="Install requirements in an isolated .venv; system tools/fonts are reported, not installed.")
    ap.add_argument("--venv", type=Path, default=ROOT / ".venv")
    ap.add_argument("--agent", choices=("claude", "codex"), help="Also require a CLI's non-billable authentication status check.")
    ap.add_argument("--json", action="store_true", help="Print a machine-readable doctor report.")
    args = ap.parse_args(argv)
    if args.install:
        try:
            return install_in_venv(args.venv, args.agent, args.json)
        except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
            print(f"[setup] {exc}", file=sys.stderr)
            return 1
    report = doctor(args.agent)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        for item in report["checks"]:
            mark = "OK" if item["ok"] is True else ("FAIL" if item["required"] else "INFO")
            print(f"[{mark}] {item['name']}: {item['detail']}")
        for key, value in report["paths"].items():
            print(f"{key}={value}")
        print("[OK] Required local runtime checks passed." if report["ok"] else "[FAIL] Required checks failed. Install Python packages with --install; fix the reported system tools/font separately.")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
