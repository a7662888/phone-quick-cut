# -*- coding: utf-8 -*-
"""素材分析：挑每支影片的精華片段、為照片評分、抓現場講話，輸出候選清單與接觸表。

  py -3 -X utf8 analyze.py --project <專案夾> [--no-speech] [--clip 5]

輸出
  02_素材\\media_index.json   候選片段 c01…（依拍攝時間排序），寫腳本時只引用這些 id
  04_QA\\素材接觸表_N.jpg     每頁 20 格縮圖，標 id、長度、分數、是否有人講話；agent 用眼睛看這張挑片
評分（0–1）：清晰度 50%、曝光 30%、晃動 20%（適度移動加分，劇烈晃動扣分）。< 0.35 標 weak，預設不選。
"""
import argparse
import datetime
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps

from pqc_common import PHOTO_EXT, VIDEO_EXT, ffprobe, find_font_path, project_dirs, read_json, run, write_json

S = 128  # 分析用縮圖邊長


def font(size):
    p = find_font_path()
    if not p:
        raise RuntimeError("缺少中文字型；請安裝 Noto Sans CJK TC 或設定 PQC_FONT_FILE")
    return ImageFont.truetype(str(p), size)


def lap_var(g):
    g = g.astype(np.float32)
    lap = -4 * g[1:-1, 1:-1] + g[:-2, 1:-1] + g[2:, 1:-1] + g[1:-1, :-2] + g[1:-1, 2:]
    return float(lap.var())


def exposure_score(mean):
    return float(max(0.0, 1 - abs(mean - 120) / 110))


def sharp_score(v):
    return float(min(1.0, math.log1p(v) / math.log1p(900)))


def open_photo(p):
    if p.suffix.lower() in {".heic", ".heif"}:
        try:
            import pillow_heif
            pillow_heif.register_heif_opener()
        except ImportError:
            raise RuntimeError("HEIC 需要 pillow-heif（py -3 -m pip install pillow-heif），或把 iPhone 相機格式改為「最相容」")
    im = ImageOps.exif_transpose(Image.open(p))
    return im.convert("RGB")


def exif_time(p):
    try:
        ex = Image.open(p).getexif()
        s = ex.get(36867) or ex.get(306)
        if s:
            return datetime.datetime.strptime(str(s)[:19], "%Y:%m:%d %H:%M:%S").isoformat()
    except Exception:
        pass
    return datetime.datetime.fromtimestamp(p.stat().st_mtime).isoformat()


def video_meta(p):
    info = ffprobe(p)
    v = next((s for s in info["streams"] if s["codec_type"] == "video"), None)
    if not v:
        return None
    w, h = int(v["width"]), int(v["height"])
    rot = 0
    for sd in v.get("side_data_list", []):
        if "rotation" in sd:
            rot = int(float(sd["rotation"]))
    rot = rot or int(v.get("tags", {}).get("rotate", 0))
    if abs(rot) % 180 == 90:
        w, h = h, w
    t = info["format"].get("tags", {}).get("creation_time") or v.get("tags", {}).get("creation_time")
    return {"w": w, "h": h, "dur": float(info["format"].get("duration", v.get("duration", 0))),
            "has_audio": any(s["codec_type"] == "audio" for s in info["streams"]),
            "time": (t or datetime.datetime.fromtimestamp(p.stat().st_mtime).isoformat())[:19]}


def video_frames(p, fps=2):
    raw = run(["ffmpeg", "-v", "error", "-i", p, "-vf", f"fps={fps},scale={S}:{S},format=gray", "-f", "rawvideo", "-"],
              text=False, encoding=None, errors=None).stdout
    return np.frombuffer(raw, np.uint8).reshape(-1, S, S)


def per_second(frames, fps=2):
    n = len(frames)
    sharp = np.array([sharp_score(lap_var(f)) for f in frames])
    expo = np.array([exposure_score(f.mean()) for f in frames])
    diff = np.r_[0, [np.abs(frames[i].astype(np.int16) - frames[i - 1]).mean() for i in range(1, n)]]
    motion = np.where(diff < 2, 0.6, np.where(diff < 25, 1.0, np.maximum(0, 1 - (diff - 25) / 30)))
    score = 0.5 * sharp + 0.3 * expo + 0.2 * motion
    return score, diff


def speech_segments(p, model):
    segs, _ = model.transcribe(str(p), language="zh", vad_filter=True,
                               initial_prompt="以下是繁體中文的日常對話。")
    return [{"start": round(s.start, 2), "end": round(s.end, 2), "text": s.text.strip()} for s in segs
            if s.no_speech_prob < 0.6 and len(s.text.strip()) >= 2]


MIN_SCENE = 1.5  # 短於此的鏡頭不單獨當候選


def scene_cuts(p):
    """PySceneDetect 找影片內的剪接點（秒）。沒裝或失敗就回空清單，退回舊行為。"""
    try:
        from scenedetect import AdaptiveDetector, detect
    except ImportError:
        return None
    try:
        scenes = detect(str(p), AdaptiveDetector(), show_progress=False)
    except Exception:
        return None
    sec = lambda tc: tc.seconds if isinstance(getattr(type(tc), "seconds", None), property) else tc.get_seconds()
    return [round(sec(s[0]), 2) for s in scenes[1:]]


def scene_of(t, cuts, dur):
    """t 所在鏡頭的 (起, 迄)。"""
    a = max([c for c in cuts if c <= t], default=0.0)
    b = min([c for c in cuts if c > t], default=dur)
    return a, b


def pick_windows(score, dur, clip, fps=2, speech=(), cuts=()):
    """在每個鏡頭內滑動視窗挑高分且不重疊的片段，不跨剪接點；落在講話上時對齊整句（不超出該鏡頭）。"""
    bounds = [0.0, *[c for c in cuts if 0 < c < dur], dur]
    scenes = [(a, b) for a, b in zip(bounds, bounds[1:]) if b - a >= MIN_SCENE]
    if not scenes:
        scenes = [(a, b) for a, b in zip(bounds, bounds[1:]) if b - a >= 0.1]
    if len(bounds) == 2 and dur <= clip + 0.5:
        return [(0.0, dur, float(score.mean()) if len(score) else 0.5)]
    k = max(1, int(clip * fps))
    opts = []  # (起, 長, 分)
    for a, b in scenes:
        seg = score[int(a * fps):max(int(a * fps) + 1, int(b * fps))]
        if b - a <= clip + 0.5:  # 短鏡頭整段當一個候選
            opts.append((a, b - a, float(seg.mean()) if len(seg) else 0.5))
            continue
        cs = np.convolve(seg, np.ones(k) / k, mode="valid")
        for i, v in enumerate(cs):
            st = a + i / fps
            if st + clip <= b + 0.01:
                opts.append((st, clip, float(v)))
    want = min(4, max(1 + int(dur // 20), len(scenes)))
    picks = []
    for st, ln, sc in sorted(opts, key=lambda o: -o[2]):
        if all(st + ln <= p[0] + 0.5 or st >= p[0] + p[1] - 0.5 for p in picks) and \
                all(abs(st - p[0]) >= min(clip, ln, p[1]) for p in picks):
            picks.append((st, ln, sc))
        if len(picks) >= want:
            break
    out = []
    for st, ln, sc in picks:
        a, b = scene_of(st + 0.01, cuts, dur)
        for s in speech:
            if s["start"] < st + ln and s["end"] > st:  # 和講話重疊 → 對齊整句（最長 12 秒、不出鏡頭）
                st = max(a, min(st, s["start"] - 0.2))
                ln = min(12.0, max(ln, s["end"] + 0.3 - st), b - st)
        out.append((round(st, 2), round(min(ln, dur - st), 2), sc))
    return sorted(out)


def contact_sheets(cands, qa_dir, per=20):
    f_big, f_small = font(26), font(20)
    paths = []
    for page in range(math.ceil(len(cands) / per)):
        chunk = cands[page * per:(page + 1) * per]
        cols, tw, th = 5, 300, 300
        rows = math.ceil(len(chunk) / cols)
        sheet = Image.new("RGB", (cols * tw, rows * (th + 56)), "white")
        dr = ImageDraw.Draw(sheet)
        for i, c in enumerate(chunk):
            x, y = (i % cols) * tw, (i // cols) * (th + 56)
            im = Image.open(c["thumb"]).convert("RGB")
            im.thumbnail((tw - 8, th - 8))
            sheet.paste(im, (x + (tw - im.width) // 2, y + (th - im.height) // 2))
            tag = f"{c['id']} {c['kind'][0].upper()} {c['dur']:.1f}s 分{c['score']:.2f}"
            dr.text((x + 6, y + th + 2), tag, fill="red" if c.get("weak") else "black", font=f_big)
            if c.get("speech_text"):
                dr.text((x + 6, y + th + 30), "說：" + c["speech_text"][:11], fill="blue", font=f_small)
        p = qa_dir / f"素材接觸表_{page + 1}.jpg"
        sheet.save(p, quality=85)
        paths.append(str(p))
    return paths


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--no-speech", action="store_true", help="不轉現場講話（較快）")
    ap.add_argument("--clip", type=float, default=5.0, help="影片精華片段的基本長度（秒）")
    ap.add_argument("--whisper", default="small")
    a = ap.parse_args()
    d = project_dirs(a.project)
    work = d["media"] / "work"
    (work / "photos").mkdir(exist_ok=True)
    (work / "thumbs").mkdir(exist_ok=True)
    model = None
    source_files = sorted((d["media"] / "src").iterdir())
    if not a.no_speech and any(f.suffix.lower() in VIDEO_EXT for f in source_files):
        from faster_whisper import WhisperModel
        model = WhisperModel(a.whisper, device="cpu", compute_type="int8")
    items, problems = [], []
    no_sd = False
    for f in source_files:
        ext = f.suffix.lower()
        try:
            if ext in PHOTO_EXT:
                im = open_photo(f)
                im.thumbnail((2400, 2400))
                norm = work / "photos" / f"{f.stem}.jpg"
                im.save(norm, quality=92)
                g = np.asarray(im.convert("L").resize((S * 4, S * 4)))
                sc = 0.6 * sharp_score(lap_var(g)) + 0.4 * exposure_score(g.mean())
                items.append({"file": f.name, "kind": "photo", "path": str(norm), "w": im.width, "h": im.height,
                              "time": exif_time(f), "windows": [(0.0, 3.5, sc)], "speech": [], "src_dur": None})
            elif ext in VIDEO_EXT:
                m = video_meta(f)
                if not m or m["dur"] < 0.8:
                    problems.append(f"{f.name}：讀不到影像或太短")
                    continue
                score, _ = per_second(video_frames(f))
                speech = speech_segments(f, model) if model and m["has_audio"] else []
                cuts = scene_cuts(f)
                if cuts is None:
                    raise RuntimeError("剪接點偵測失敗；請檢查 scenedetect 安裝與影片格式")
                wins = pick_windows(score, m["dur"], a.clip, speech=speech, cuts=cuts)
                items.append({"file": f.name, "kind": "video", "path": str(f), "w": m["w"], "h": m["h"],
                              "time": m["time"], "windows": wins, "speech": speech, "src_dur": m["dur"],
                              "has_audio": m["has_audio"], "cuts": cuts})
        except Exception as e:  # 單一檔案壞掉不擋整批
            problems.append(f"{f.name}：{e}")
    items.sort(key=lambda it: it["time"])
    cands, n = [], 0
    for it in items:
        for st, ln, sc in it["windows"]:
            n += 1
            cid = f"c{n:02d}"
            thumb = work / "thumbs" / f"{cid}.jpg"
            if it["kind"] == "photo":
                im = Image.open(it["path"])
                im.thumbnail((400, 400))
                im.save(thumb, quality=80)
            else:
                run(["ffmpeg", "-v", "error", "-y", "-ss", f"{st + ln / 2:.2f}", "-i", it["path"], "-frames:v", "1",
                     "-vf", "scale=400:400:force_original_aspect_ratio=decrease", thumb])
            said = " ".join(s["text"] for s in it["speech"] if s["start"] < st + ln and s["end"] > st)
            c = {"id": cid, "file": it["file"], "kind": it["kind"], "path": it["path"], "in": st,
                 "dur": ln, "src_dur": it["src_dur"], "w": it["w"], "h": it["h"], "time": it["time"],
                 "score": round(sc, 3), "weak": sc < 0.35, "has_audio": it.get("has_audio", False),
                 "speech_text": said, "thumb": str(thumb)}
            if it["kind"] == "video":  # 該鏡頭的起迄，build.py 延長時不跨剪接點
                c["scene"] = [round(x, 2) for x in scene_of(st + 0.01, it["cuts"], it["src_dur"])]
            cands.append(c)
    sheets = contact_sheets(cands, d["qa"]) if cands else []
    idx = {"project": str(Path(a.project)), "candidates": cands, "problems": problems, "contact_sheets": sheets,
           "total_candidate_seconds": round(sum(c["dur"] for c in cands if not c["weak"]), 1)}
    write_json(d["media"] / "media_index.json", idx)
    if not cands:
        raise SystemExit("[analyze] 沒有可用候選片段；" + "；".join(problems))
    print(f"[analyze] 候選 {len(cands)} 段（weak {sum(c['weak'] for c in cands)}），可用約 {idx['total_candidate_seconds']} 秒")
    if no_sd:
        print("[analyze] ⚠ 沒有 scenedetect，挑段不偵測剪接點（py -3 -m pip install scenedetect）")
    for p in problems:
        print(f"[analyze] ⚠ {p}")
    for s in sheets:
        print(f"[analyze] 接觸表：{s}")


if __name__ == "__main__":
    main()
