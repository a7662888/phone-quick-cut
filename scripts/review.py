# -*- coding: utf-8 -*-
"""台詞審閱關卡：腳本寫好後、合成前，把台詞稿與分鏡預覽放到收件匣子夾，等業主確認。

  py -3 -X utf8 review.py --project <專案>

產出（收件匣子夾，手機上直接看）
  _台詞稿.txt     每鏡的大約時間、素材檔名、旁白、字卡；片名、片尾、配樂
  _分鏡預覽.jpg   選用畫面縮圖＋編號＋旁白，對照台詞稿用
專案內另存 01_查核與腳本\\台詞稿.txt 與 04_QA\\分鏡預覽.jpg。
業主回覆：放「確認」開頭的檔＝同意合成；放「修改」開頭的語音或文字＝改台詞後再送審。
"""
import argparse
import hashlib
import math
import shutil
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw

from analyze import font
from pqc_common import project_dirs, read_json, write_json

VOICE_NAME = {"zh-TW-YunJheNeural": "男聲", "zh-TW-HsiaoChenNeural": "女聲", "zh-TW-HsiaoYuNeural": "女聲2"}


def mmss(s):
    return f"{int(s // 60)}:{int(s % 60):02d}"


def estimate(script, cands):
    rows, t = [], 0.0
    for i, s in enumerate(script["shots"], 1):
        c = cands[s["cand"]]
        dur = float(s.get("dur", c["dur"]))
        nar = s.get("narration", "")
        ln = max(dur, 0.25 + len(nar) / 4.2 + 0.45 if nar else 0, 1.0)
        rows.append((i, t, t + ln, c, s))
        t += ln
    return rows, t


def preview(rows, out, per_row=3):
    tw, th, cap = 360, 360, 130
    n = len(rows)
    sheet = Image.new("RGB", (per_row * tw, math.ceil(n / per_row) * (th + cap)), "white")
    dr = ImageDraw.Draw(sheet)
    f_num, f_txt = font(30), font(22)
    for k, (i, t0, t1, c, s) in enumerate(rows):
        x, y = (k % per_row) * tw, (k // per_row) * (th + cap)
        im = Image.open(c["thumb"]).convert("RGB")
        im.thumbnail((tw - 10, th - 10))
        sheet.paste(im, (x + (tw - im.width) // 2, y + (th - im.height) // 2))
        dr.rectangle([x + 6, y + 6, x + 92, y + 46], fill="black")
        dr.text((x + 12, y + 8), f"{i:02d}", fill="white", font=f_num)
        body = s.get("narration") or ("（現場原音）" if s.get("keep_audio") else "（無旁白）")
        if s.get("caption"):
            body = f"【{s['caption']}】" + body
        for j, line in enumerate(textwrap.wrap(body, 15)[:4]):
            dr.text((x + 8, y + th + 4 + j * 30), line, fill="black", font=f_txt)
    sheet.save(out, quality=85)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    a = ap.parse_args()
    d = project_dirs(a.project)
    script = read_json(d["script"] / "script.json")
    brief = read_json(d["script"] / "brief.json", {})
    cands = {c["id"]: c for c in read_json(d["media"] / "media_index.json")["candidates"]}
    rows, total = estimate(script, cands)
    m = script.get("music", {})
    voice_label = VOICE_NAME.get(script["voice"], script["voice"]) if any(s.get("narration") for s in script["shots"]) else "無旁白"
    lines = [f"【台詞稿】{script['title']}",
             f"{script['style']}｜{script['ratio']}｜{voice_label}｜約 {round(total)} 秒"
             f"（目標 {brief.get('target_seconds', '?')} 秒）",
             f"片尾字卡：{script.get('outro') or '（無）'}",
             f"配樂：{'無' if not m.get('enabled', True) else m.get('prompt', '自動')}",
             f"寫稿模式：{script.get('_meta', {}).get('written_by', '目前 Agent／手動')}"
             "（template 為保底模板，llm 不會看畫面；請核對內容）", ""]
    for i, t0, t1, c, s in rows:
        lines.append(f"{i:02d}  {mmss(t0)}–{mmss(t1)}  {c['file']}")
        if s.get("caption"):
            lines.append(f"    字卡：{s['caption']}")
        if s.get("narration"):
            lines.append(f"    旁白：{s['narration']}")
        elif s.get("keep_audio"):
            lines.append(f"    現場原音：{s.get('speech_caption') or c.get('speech_text') or '（保留）'}")
        else:
            lines.append("    （無旁白）")
    lines += ["", "──── 怎麼回覆 ────",
              "手動模式：回覆目前的 Agent，確認後由 Agent 執行 --approve；要改先告知 Agent，再重新送審。",
              "已啟用背景掃描時：放一個「確認」開頭的檔表示同意；放「修改」開頭的語音或文字表示改稿。",
              "對照圖：_分鏡預覽.jpg（編號同上，只供選片與台詞核對；標題遮擋需看合成草稿）"]
    text = "\n".join(lines)
    (d["script"] / "台詞稿.txt").write_text(text, encoding="utf-8")
    prev = d["qa"] / "分鏡預覽.jpg"
    preview(rows, prev)
    write_json(d["script"] / "review.json", {"script_sha256": hashlib.sha256((d["script"] / "script.json").read_bytes()).hexdigest()})
    inbox = brief.get("inbox_folder")
    if inbox and Path(inbox).exists():
        Path(inbox, "_台詞稿.txt").write_text(text, encoding="utf-8")
        shutil.copy2(prev, Path(inbox, "_分鏡預覽.jpg"))
    print(text)
    print(f"\n[review] 分鏡預覽：{prev}")


if __name__ == "__main__":
    main()
