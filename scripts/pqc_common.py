# -*- coding: utf-8 -*-
"""phone-quick-cut 共用設定與工具函式。本機（Windows）與 Colab（Linux）共用同一份。

路徑可用環境變數覆蓋：
  PQC_INBOX   收件匣（預設 E:\\OneDrive\\手機快剪\\收件匣）
  PQC_OUTBOX  成品夾（預設 E:\\OneDrive\\手機快剪\\成品）
  PQC_VIDEO   影片專案母夾（預設 D:\\secondbrain\\Video）
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

def _default_dir(env_key, win_legacy, win_fallback, colab_path):
    if env_key in os.environ and os.environ[env_key].strip():
        return Path(os.environ[env_key])
    if ON_COLAB:
        return Path(colab_path)
    if IS_WIN and Path(win_legacy).exists():
        return Path(win_legacy)
    return Path(win_fallback)


def _detect_onedrive_root():
    for env in ("OneDriveCommercial", "OneDriveConsumer", "OneDrive"):
        v = os.environ.get(env)
        if v and Path(v).exists():
            return Path(v)
    od = Path.home() / "OneDrive"
    return od if od.exists() else (Path.home() / "Videos")


_OD_BASE = _detect_onedrive_root() / "手機快剪"
INBOX = _default_dir("PQC_INBOX", r"E:\OneDrive\手機快剪\收件匣", _OD_BASE / "收件匣", "/content/pqc/inbox")
OUTBOX = _default_dir("PQC_OUTBOX", r"E:\OneDrive\手機快剪\成品", _OD_BASE / "成品", "/content/pqc/outbox")
VIDEO_ROOT = _default_dir("PQC_VIDEO", r"D:\secondbrain\Video", Path.home() / "Videos" / "PhoneQuickCut", "/content/pqc/projects")

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
FONT = "Noto Sans TC" if IS_WIN else "Noto Sans CJK TC"  # Colab 的 fonts-noto-cjk 家族名不同
MAX_SECONDS = 180


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
    """edge-tts.exe 啟動器在本機被應用程式控制原則封鎖，一律用 python -m edge_tts。"""
    uv_py = Path.home() / "AppData/Roaming/uv/tools/edge-tts/Scripts/python.exe"
    py = str(uv_py) if IS_WIN and uv_py.exists() else sys.executable
    return [py, "-m", "edge_tts"]


def apply_pron(text):
    """套共用讀音表（只影響送 TTS 的字串，字幕仍用原字）；Colab 上沒有就原樣回傳。"""
    shared = Path(__file__).resolve().parents[2] / "_shared" / "scripts"
    if (shared / "tts_pron.py").exists():
        sys.path.insert(0, str(shared))
        try:
            from tts_pron import apply_text  # noqa
            return apply_text(text, "edge")[0]
        except Exception:
            return text
    return text


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
