# -*- coding: utf-8 -*-
"""檢查並安裝 phone-quick-cut 所需環境（假設使用者電腦尚未安裝任何相依軟體）。

用法：
  python scripts/setup_env.py            # 只檢查狀態並印出缺漏清單
  python scripts/setup_env.py --install  # 自動補齊 Python 套件並建立收件匣/成品資料夾
"""
import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pqc_common import INBOX, OUTBOX, VIDEO_ROOT

REQUIRED_MODULES = [
    ("edge_tts", "edge-tts"),
    ("faster_whisper", "faster-whisper"),
    ("scenedetect", "scenedetect[opencv]"),
    ("cv2", "opencv-python"),
    ("PIL", "pillow"),
    ("pillow_heif", "pillow-heif"),
    ("numpy", "numpy"),
    ("requests", "requests"),
]


def check_ffmpeg():
    ff = shutil.which("ffmpeg")
    fp = shutil.which("ffprobe")
    return bool(ff and fp), ff, fp


def check_modules():
    missing = []
    for mod, pkg in REQUIRED_MODULES:
        try:
            __import__(mod)
        except Exception:
            missing.append((mod, pkg))
    return missing


def install_ffmpeg_hint():
    sysname = platform.system()
    if sysname == "Windows":
        return "winget install -e --id Gyan.FFmpeg  (安裝後請重開終端機讓 PATH 生效)"
    if sysname == "Darwin":
        return "brew install ffmpeg"
    return "sudo apt-get update && sudo apt-get install -y ffmpeg"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--install", action="store_true", help="自動 pip 安裝缺少套件並建立資料夾")
    args = ap.parse_args()

    print(f"[setup] Python: {sys.version.split()[0]} ({sys.executable})")
    ff_ok, ff_path, fp_path = check_ffmpeg()
    print(f"[setup] FFmpeg: {'OK -> ' + ff_path if ff_ok else 'MISSING!'}")
    print(f"[setup] ffprobe: {'OK -> ' + fp_path if ff_ok else 'MISSING!'}")

    missing = check_modules()
    if missing:
        print("[setup] 缺少 Python 套件：", ", ".join(pkg for _, pkg in missing))
    else:
        print("[setup] Python 套件：全部就緒")

    if args.install:
        if not ff_ok and platform.system() == "Windows" and shutil.which("winget"):
            print("[setup] 嘗試透過 winget 安裝 FFmpeg...")
            subprocess.run(["winget", "install", "-e", "--id", "Gyan.FFmpeg", "--accept-package-agreements", "--accept-source-agreements"], check=False)
        if missing:
            req = Path(__file__).resolve().parents[1] / "requirements.txt"
            print(f"[setup] 安裝 requirements.txt：{req}")
            subprocess.run([sys.executable, "-m", "pip", "install", "-r", str(req)], check=True)
        for d in (INBOX, OUTBOX, VIDEO_ROOT):
            d.mkdir(parents=True, exist_ok=True)
            print(f"[setup] 資料夾就緒：{d}")

    print("\n--- 目錄設定 ---")
    print(f"  收件匣 (PQC_INBOX) : {INBOX}")
    print(f"  成品夾 (PQC_OUTBOX): {OUTBOX}")
    print(f"  專案夾 (PQC_VIDEO) : {VIDEO_ROOT}")

    ff_ok_after, _, _ = check_ffmpeg()
    missing_after = check_modules()
    if not ff_ok_after:
        print(f"\n[!] 尚未偵測到 FFmpeg，請執行：\n    {install_ffmpeg_hint()}")
    if missing_after and not args.install:
        print("\n[!] 請執行以下指令自動安裝 Python 套件與建立資料夾：\n    python scripts/setup_env.py --install")
    if ff_ok_after and not missing_after:
        print("\n[OK] 所有必要軟體皆已就緒，可以開始使用 phone-quick-cut！")


if __name__ == "__main__":
    main()
