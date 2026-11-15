# -*- coding: utf-8 -*-
"""收件：把收件匣裡的一個子夾建成影片專案，並把語音任務單轉成 brief.json。

  python -X utf8 intake.py --src "<收件匣子夾>" [--project <既有專案夾>]

- 素材「複製」進 02_素材\\src，不移動、不改名、不刪收件匣原檔。
- 任務單：純音訊檔（語音備忘）或 任務.txt。語音用 faster-whisper（CPU）轉文字，再以關鍵字解析：
  主題、風格（創意／溫馨／幽默／知識／藝術）、長度、比例（9:16／16:9／1:1／4:5）、男聲或女聲、要不要音樂、保留原音。
- 解析不到的欄位用預設值，並在 brief.json 的 "guessed" 列出，由寫腳本的 agent 再確認。
"""
import argparse
import datetime
import re
import shutil
from pathlib import Path

from pqc_common import (APPROVE_NAMES, AUDIO_EXT, BRIEF_TXT, MAX_SECONDS, PHOTO_EXT, REVISE_NAMES, VIDEO_EXT, VIDEO_ROOT, VOICES,
                        project_dirs, safe_name, write_json)

CN_NUM = {"零": 0, "一": 1, "二": 2, "兩": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
STYLE_WORDS = {
    "溫馨": ["溫馨", "温馨", "溫暖", "温暖", "感人", "感性", "家人", "回憶"],
    "幽默": ["幽默", "搞笑", "好笑", "逗趣", "爆笑", "吐槽"],
    "知識": ["知識", "知识", "科普", "教學", "教学", "介紹", "介绍", "導覽", "导览"],
    "藝術": ["藝術", "艺术", "文青", "詩意", "诗意", "唯美", "電影感", "电影感"],
    "創意": ["創意", "创意", "有趣", "特別", "特别", "酷"],
}
RATIO_WORDS = {
    "9:16": ["直式", "直的", "直立", "豎", "竖", "9比16", "9:16", "reels", "shorts", "限時動態", "限时动态"],
    "16:9": ["橫式", "横式", "橫的", "横的", "16比9", "16:9", "youtube", "電視", "电视"],
    "1:1": ["方形", "正方", "1比1", "1:1"],
    "4:5": ["4比5", "4:5", "貼文", "贴文"],
}


def cn_to_num(s):
    if s.isdigit():
        return int(s)
    if s == "十":
        return 10
    if "十" in s:
        a, _, b = s.partition("十")
        return (CN_NUM.get(a, 1) if a else 1) * 10 + (CN_NUM.get(b, 0) if b else 0)
    return CN_NUM.get(s, 0)


def parse_length(t):
    t = t.replace("鐘", "").replace("钟", "")
    m = re.search(r"([0-9一二兩两三四五六七八九十]+)\s*分\s*半", t)
    if m:
        return cn_to_num(m.group(1)) * 60 + 30
    m = re.search(r"([0-9一二兩两三四五六七八九十]+)\s*分\s*([0-9一二兩两三四五六七八九十]+)\s*秒", t)
    if m:
        return cn_to_num(m.group(1)) * 60 + cn_to_num(m.group(2))
    m = re.search(r"([0-9一二兩两三四五六七八九十]+)\s*分", t)
    if m:
        return cn_to_num(m.group(1)) * 60
    m = re.search(r"([0-9一二兩两三四五六七八九十]+)\s*秒", t)
    if m:
        return cn_to_num(m.group(1))
    if "半分" in t:
        return 30
    return None


def parse_brief(text, fallback_title):
    t = text.lower()
    brief, guessed = {"raw": text}, []
    m = re.search(r"(?:主題|主题|題目|题目|片名|標題|标题)(?:是|為|为|叫|：|:)?\s*([^，,。.！!？?\n]{1,30})", text)
    brief["theme"] = m.group(1).strip() if m else fallback_title
    if not m:
        guessed.append("theme")
    brief["style"] = next((k for k, ws in STYLE_WORDS.items() if any(w in t for w in ws)), None)
    if not brief["style"]:
        brief["style"], _ = "溫馨", guessed.append("style")
    sec = parse_length(text)
    brief["target_seconds"] = min(MAX_SECONDS, max(1, sec)) if sec else 90
    if not sec:
        guessed.append("target_seconds")
    brief["ratio"] = next((k for k, ws in RATIO_WORDS.items() if any(w in t for w in ws)), None)
    if not brief["ratio"]:
        brief["ratio"], _ = "9:16", guessed.append("ratio")
    if any(w in t for w in ["女聲", "女声", "女生", "女的"]):
        brief["voice"] = VOICES["女"]
    elif any(w in t for w in ["男聲", "男声", "男生", "男的"]):
        brief["voice"] = VOICES["男"]
    else:
        brief["voice"] = VOICES["男"]
        guessed.append("voice")
    brief["music"] = not any(w in t for w in ["不要音樂", "不要音乐", "無音樂", "无音乐", "不用音樂", "不用音乐", "沒有音樂"])
    brief["keep_original_audio"] = any(w in t for w in ["保留原音", "原音", "現場聲音", "现场声音"])
    brief["no_narration"] = any(w in t for w in ["不要旁白", "不要配音", "不用配音", "無旁白"])
    brief["guessed"] = guessed
    return brief


def transcribe(audio, model="large-v3-turbo"):  # 任務單很短，用準的模型（small 會把「週末」聽成「周目」）
    from faster_whisper import WhisperModel
    m = WhisperModel(model, device="cpu", compute_type="int8")
    segs, _ = m.transcribe(str(audio), language="zh", initial_prompt="以下是繁體中文的錄音，主題、風格、長度、直式或橫式。", vad_filter=True)
    return "".join(s.text for s in segs).strip()


def classify(src, with_approvals=False):
    """回傳 (素材, 任務單, 修改檔)；with_approvals=True 時多回傳「確認」檔。確認檔不會被當成任務單。"""
    media, briefs, revises, approves = [], [], [], []
    for f in sorted(Path(src).iterdir()):
        if f.name.startswith(("_", ".")) or not f.is_file():
            continue
        ext = f.suffix.lower()
        is_rev = f.stem.startswith(REVISE_NAMES)
        if f.stem.startswith(APPROVE_NAMES) and ext not in VIDEO_EXT | PHOTO_EXT:
            approves.append(f)
            continue
        if f.name in BRIEF_TXT or (ext == ".txt" and not is_rev):
            briefs.append(f)
        elif ext in AUDIO_EXT or (ext == ".txt" and is_rev):
            (revises if is_rev else briefs).append(f)
        elif ext in VIDEO_EXT | PHOTO_EXT:
            media.append(f)
    return (media, briefs, revises, approves) if with_approvals else (media, briefs, revises)


def brief_text(files):
    parts = []
    for f in files:
        parts.append(f.read_text(encoding="utf-8-sig", errors="replace") if f.suffix.lower() == ".txt" else transcribe(f))
    return "\n".join(p for p in parts if p)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True, help="收件匣裡的子夾")
    ap.add_argument("--project", help="沿用既有專案（修改模式）")
    a = ap.parse_args()
    src = Path(a.src).expanduser().resolve()
    media, briefs, _ = classify(src)
    if not media:
        raise SystemExit(f"{src} 裡沒有照片或影片")
    text = brief_text(briefs) if briefs else ""
    brief = parse_brief(text, src.name)
    brief["inbox_folder"] = str(src)
    brief["brief_files"] = [f.name for f in briefs]
    if a.project:
        proj = Path(a.project).expanduser().resolve()
    else:
        proj = VIDEO_ROOT / f"{datetime.date.today():%Y%m%d}_手機快剪_{safe_name(brief['theme'])}"
        n = 2
        while proj.exists():
            proj = proj.with_name(f"{proj.name.split('_v')[0]}_v{n}")
            n += 1
    d = project_dirs(proj)
    for f in media:
        dst = d["media"] / "src" / f.name
        if not dst.exists() or dst.stat().st_size != f.stat().st_size:
            shutil.copy2(f, dst)
    write_json(d["script"] / "brief.json", brief)
    (d["script"] / "任務單逐字稿.txt").write_text(text or "（沒有任務單，全部用預設值）", encoding="utf-8")
    print(f"[intake] 專案：{proj}")
    print(f"[intake] 素材 {len(media)} 個；任務單：{text[:80] or '（無）'}")
    print(f"[intake] 解析：{ {k: brief[k] for k in ('theme', 'style', 'target_seconds', 'ratio', 'voice', 'music')} }；猜的欄位：{brief['guessed']}")
    print(f"PROJECT={proj}")


if __name__ == "__main__":
    main()
