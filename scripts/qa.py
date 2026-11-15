# -*- coding: utf-8 -*-
"""成片 QA：長度、響度、真峰值、黑畫面、字幕行長、旁白聽寫比對，並產 3×3 成片接觸表。

  py -3 -X utf8 qa.py --project <專案> [--file <成片.mp4>] [--no-listen]

結果寫 04_QA\\qa.json；有任何 FAIL 時結束碼為 1。WARN 不擋交付，但要在回報裡說。
"""
import argparse
import json
import re
import sys
from pathlib import Path

from PIL import Image

from pqc_common import MAX_SECONDS, duration, project_dirs, read_json, run, write_json


def loudness(f):
    r = run(["ffmpeg", "-hide_banner", "-nostats", "-i", f, "-af", "ebur128=peak=true", "-f", "null", "-"])
    s = r.stderr
    i = re.findall(r"I:\s+(-?[\d.]+) LUFS", s)
    p = re.findall(r"Peak:\s+(-?[\d.]+) dBFS", s)
    return (float(i[-1]) if i else None), (float(p[-1]) if p else None)


def black_spans(f):
    r = run(["ffmpeg", "-hide_banner", "-nostats", "-i", f, "-vf", "blackdetect=d=0.8:pix_th=0.08", "-an", "-f", "null", "-"])
    return [(float(a), float(b)) for a, b in re.findall(r"black_start:([\d.]+) black_end:([\d.]+)", r.stderr)]


def grid(f, dur, out):
    tiles = []
    for k in range(9):
        t = dur * (k + 0.5) / 9
        p = out.parent / f"_g{k}.jpg"
        run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.2f}", "-i", f, "-frames:v", "1", "-vf", "scale=360:-2", p])
        tiles.append(Image.open(p).convert("RGB"))
    w, h = tiles[0].size
    sheet = Image.new("RGB", (w * 3, h * 3), "white")
    for k, im in enumerate(tiles):
        sheet.paste(im, ((k % 3) * w, (k // 3) * h))
    sheet.save(out, quality=85)
    for k in range(9):
        (out.parent / f"_g{k}.jpg").unlink(missing_ok=True)


def cer(ref, hyp):
    ref, hyp = re.sub(r"\W", "", ref), re.sub(r"\W", "", hyp)
    if not ref:
        return 0.0
    dp = list(range(len(hyp) + 1))
    for i in range(1, len(ref) + 1):
        prev, dp[0] = dp[0], i
        for j in range(1, len(hyp) + 1):
            cur = dp[j]
            dp[j] = min(dp[j] + 1, dp[j - 1] + 1, prev + (ref[i - 1] != hyp[j - 1]))
            prev = cur
    return dp[-1] / len(ref)


def listen(narr_wav, ref):
    from faster_whisper import WhisperModel
    m = WhisperModel("small", device="cpu", compute_type="int8")
    segs, _ = m.transcribe(str(narr_wav), language="zh", initial_prompt="以下是繁體中文旁白。")
    hyp = "".join(s.text for s in segs)
    try:  # Whisper 常吐簡體：有 opencc 就轉繁再比
        import opencc
        hyp = opencc.OpenCC("s2twp").convert(hyp)
    except ImportError:
        pass
    return cer(ref, hyp), hyp


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--file")
    ap.add_argument("--no-listen", action="store_true")
    a = ap.parse_args()
    d = project_dirs(a.project)
    tl = read_json(d["out"] / "timeline.json")
    brief = read_json(d["script"] / "brief.json", {})
    f = Path(a.file or tl["final"])
    res, fails, warns = {"file": str(f)}, [], []
    dur = duration(f)
    res["duration"] = round(dur, 2)
    if dur > MAX_SECONDS + 0.5:
        fails.append(f"長度 {dur:.1f} 秒 > 180 秒")
    tgt = brief.get("target_seconds")
    if tgt and abs(dur - tgt) > max(15, tgt * 0.25):
        warns.append(f"長度 {dur:.0f} 秒和任務單 {tgt} 秒差距大（素材不夠或腳本太短／太長）")
    li, peak = loudness(f)
    res.update(lufs=li, true_peak=peak)
    if li is None or not (-19 <= li <= -13):
        warns.append(f"整體響度 {li} LUFS（目標 -16）")
    if peak is not None and peak > -0.5:
        fails.append(f"真峰值 {peak} dBFS 會破音")
    bl = [s for s in black_spans(f) if s[0] > 0.5 and s[1] < dur - 1.0]
    res["black"] = bl
    if bl:
        fails.append(f"片中有黑畫面：{bl}")
    if tl.get("voice_requested"):
        warns.append(f"指定聲音 {tl['voice_requested']} 當時無法合成，已改用 {tl['voice']}；可稍後修改重剪換回")
    if not tl.get("music") and read_json(d["script"] / "script.json", {}).get("music", {}).get("enabled", True):
        warns.append("配樂生成失敗，成片沒有音樂")
    elif tl.get("music") and "synth" in str(tl["music"]):
        warns.append("配樂用保底合成和弦（Lyria／MusicGen 失敗），音質普通")
    script = read_json(d["script"] / "script.json")
    ref = "".join(s.get("narration", "") for s in script["shots"])
    narr = d["media"] / "work" / ("d_narration.wav" if "草稿" in f.name else "f_narration.wav")
    if ref and not a.no_listen and narr.exists():
        e, hyp = listen(narr, ref)
        res.update(narration_cer=round(e, 3), heard=hyp)
        if e > 0.2:
            warns.append(f"旁白聽寫差異率 {e:.0%}，請人耳試聽（可能是讀音錯或 Whisper 聽錯）")
    sheet = d["qa"] / "成片接觸表.jpg"
    grid(f, dur, sheet)
    res.update(contact_sheet=str(sheet), fails=fails, warns=warns, verdict="FAIL" if fails else "PASS")
    write_json(d["qa"] / "qa.json", res)
    print(json.dumps({k: res[k] for k in ("duration", "lufs", "true_peak", "verdict", "fails", "warns")}, ensure_ascii=False))
    print(f"[qa] 成片接觸表：{sheet}（交付前請用眼睛看這張）")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
