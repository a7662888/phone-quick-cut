# -*- coding: utf-8 -*-
"""phone-quick-cut 共用設定與工具函式。本機（Windows）與 Colab（Linux）共用同一份。

路徑可用 PQC_INBOX、PQC_OUTBOX、PQC_VIDEO 覆蓋；預設使用當前使用者的目錄。
"""
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

IS_WIN = os.name == "nt"
ON_COLAB = "COLAB_RELEASE_TAG" in os.environ or Path("/content").exists() and not IS_WIN

def _default_dir(env_key, fallback, colab_path):
    if env_key in os.environ and os.environ[env_key].strip():
        return Path(os.environ[env_key]).expanduser().resolve()
    if ON_COLAB:
        return Path(colab_path)
    return Path(fallback).expanduser().resolve()


def _detect_onedrive_root():
    for env in ("OneDriveCommercial", "OneDriveConsumer", "OneDrive"):
        v = os.environ.get(env)
        if v and Path(v).exists():
            return Path(v)
    for od in [Path.home() / "OneDrive", *sorted((Path.home() / "Library" / "CloudStorage").glob("OneDrive-*"))]:
        if od.is_dir():
            return od
    return Path.home() / "Videos"


_OD_BASE = _detect_onedrive_root() / "手機快剪"
INBOX = _default_dir("PQC_INBOX", _OD_BASE / "收件匣", "/content/pqc/inbox")
OUTBOX = _default_dir("PQC_OUTBOX", _OD_BASE / "成品", "/content/pqc/outbox")
VIDEO_ROOT = _default_dir("PQC_VIDEO", Path.home() / "Videos" / "PhoneQuickCut", "/content/pqc/projects")

VIDEO_EXT = {".mp4", ".mov", ".m4v", ".3gp", ".mkv", ".webm", ".avi"}
PHOTO_EXT = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif", ".bmp"}
AUDIO_EXT = {".m4a", ".mp3", ".wav", ".aac", ".opus", ".ogg", ".amr", ".flac", ".3ga"}
BRIEF_TXT = {"任務.txt", "brief.txt", "任務單.txt"}
REVISE_NAMES = ("修改", "revise", "改")
APPROVE_NAMES = ("確認", "确认", "同意", "OK", "ok", "Ok")

RATIOS = {"9:16": (1080, 1920), "16:9": (1920, 1080), "1:1": (1080, 1080), "4:5": (1080, 1350)}
VOICES = {"男": "zh-TW-YunJheNeural", "女": "zh-TW-HsiaoChenNeural", "女2": "zh-TW-HsiaoYuNeural"}
STYLES = ("創意", "溫馨", "幽默", "知識", "藝術")
FPS = 30
FONT = os.environ.get("PQC_FONT_FAMILY", "Noto Sans CJK TC")
MAX_SECONDS = 180
SKILL_ROOT = Path(__file__).resolve().parents[1]


def find_font_path():
    """Find a CJK font without downloading or changing system configuration."""
    custom = os.environ.get("PQC_FONT_FILE")
    if custom:
        p = Path(custom).expanduser().resolve()
        return p if p.is_file() else None
    candidates = [
        *sorted((SKILL_ROOT / "assets" / "fonts").glob("*.[ot]tf")),
        Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "NotoSansTC-VF.ttf",
        Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "msjh.ttc",
        Path("/System/Library/Fonts/PingFang.ttc"),
        Path("/System/Library/Fonts/STHeiti Medium.ttc"),
        Path("/Library/Fonts/Arial Unicode.ttf"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"),
    ]
    for p in candidates:
        if p.is_file():
            return p
    if shutil.which("fc-match"):
        r = subprocess.run(["fc-match", "-f", "%{file}", "sans:lang=zh-tw"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10)
        p = Path(r.stdout.strip())
        if r.returncode == 0 and p.is_file() and any(s in p.name.lower() for s in ("noto", "cjk", "han", "hei", "ming", "ukai", "uming")):
            return p
    return None


def font_family():
    if os.environ.get("PQC_FONT_FAMILY"):
        return os.environ["PQC_FONT_FAMILY"]
    p = find_font_path()
    if p:
        from PIL import ImageFont
        return ImageFont.truetype(str(p), 20).getname()[0]
    return FONT


def env_enabled(name):
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes")


def api_key():
    """Only an explicitly configured environment key; never search other projects."""
    return os.environ.get("OPENROUTER_API_KEY", "").strip()


def run(cmd, **kw):
    """執行外部指令；失敗時把 stderr 尾段印出來再中止。"""
    kw.setdefault("capture_output", True)
    kw.setdefault("text", True)
    kw.setdefault("encoding", "utf-8")
    kw.setdefault("errors", "replace")
    kw.setdefault("timeout", 3600)  # 防死鎖：任何一支外部指令超過 1 小時就中止
    cmd = [str(c) for c in cmd]
    if cmd[0] == "ffmpeg" and "-nostdin" not in cmd:  # 背景／排程執行時 ffmpeg 讀 stdin 會卡住
        cmd.insert(1, "-nostdin")
    r = subprocess.run(cmd, **kw)
    if r.returncode:
        sys.exit(f"指令失敗：{' '.join(map(str, cmd[:6]))} …\n{(r.stderr or '')[-1500:]}")
    return r


def ffprobe(path):
    r = run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", path])
    return json.loads(r.stdout)


def duration(path):
    r = run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path])
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def read_json(p, default=None):
    p = Path(p)
    if not p.exists():
        return default
    return json.loads(p.read_text(encoding="utf-8"))


def write_json(p, obj):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    Path(p).write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def project_dirs(proj):
    proj = Path(proj)
    d = {k: proj / v for k, v in {"script": "01_查核與腳本", "media": "02_素材", "out": "03_成片", "qa": "04_QA"}.items()}
    for p in d.values():
        p.mkdir(parents=True, exist_ok=True)
    (d["media"] / "src").mkdir(exist_ok=True)
    (d["media"] / "work").mkdir(exist_ok=True)
    return d


def safe_name(s, n=24):
    s = re.sub(r'[\\/:*?"<>|\s]+', "_", s).strip("_")
    return s[:n] or "未命名"


def edge_tts_cmd():
    """Use exactly the environment verified by doctor; avoid the .exe launcher."""
    return [sys.executable, "-m", "edge_tts"]


def apply_pron(text):
    """Bundled replacements affect TTS only, never displayed captions."""
    p = Path(os.environ.get("PQC_PRONUNCIATION", str(SKILL_ROOT / "assets" / "pronunciation_zh.json"))).expanduser()
    data = read_json(p)
    if not isinstance(data, dict) or not isinstance(data.get("entries"), list):
        raise ValueError(f"讀音表不存在或格式錯誤：{p}")
    entries = [e for e in data["entries"] if e.get("kind", "sub") == "sub"
               and ("all" in e.get("engines", ["all"]) or "edge" in e.get("engines", ["all"]))]
    mapping = {e["src"]: e["say"] for e in entries if e.get("src") and isinstance(e.get("say"), str)}
    if not mapping:
        return text
    pattern = "|".join(re.escape(s) for s in sorted(mapping, key=len, reverse=True))
    return re.sub(pattern, lambda m: mapping[m.group(0)], text)


def latest_exe(pattern_dir, name):
    """找版本號資料夾裡最新的 claude.exe／codex.exe（更新後路徑會變）。"""
    base = Path(pattern_dir)
    if not base.exists():
        return None
    hits = sorted(base.rglob(name), key=lambda p: p.stat().st_mtime, reverse=True)
    return str(hits[0]) if hits else None


def find_agent(agent):
    if agent == "claude":
        return shutil.which("claude") or latest_exe(Path(os.environ.get("LOCALAPPDATA", "")) / "Claude-Data", "claude.exe")
    if agent == "codex":
        return shutil.which("codex") or latest_exe(Path(os.environ.get("LOCALAPPDATA", "")) / "OpenAI" / "Codex" / "bin", "codex.exe")
    return None


def agent_command(agent):
    """Avoid feeding untrusted prompts to Windows batch-file launchers."""
    exe = find_agent(agent)
    if not exe:
        raise RuntimeError(f"找不到 {agent} CLI；請安裝並登入，或使用 --mode manual／template")
    p = Path(exe)
    if p.suffix.lower() in (".cmd", ".bat"):
        package = {"codex": "@openai/codex/bin/codex.js", "claude": "@anthropic-ai/claude-code/cli.js"}[agent]
        js = p.parent / "node_modules" / package
        node = shutil.which("node")
        if not (js.is_file() and node):
            raise RuntimeError(f"{agent} 只有 batch 啟動器，找不到對應 Node CLI；請改用 --mode manual")
        return [node, str(js)]
    return [exe]
