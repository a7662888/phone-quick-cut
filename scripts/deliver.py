# -*- coding: utf-8 -*-
"""交付：成片複製到 OneDrive「成品」夾、在收件匣子夾寫 _狀態.txt（手機上就看得到）、寫專案 HANDOFF.md。

  py -3 -X utf8 deliver.py --project <專案> [--status 完成|失敗] [--note "…"]
"""
import argparse
import datetime
import shutil
from pathlib import Path

from pqc_common import OUTBOX, project_dirs, read_json


def status_file(brief, status, lines, processed=""):
    """寫 _狀態.txt；「已處理」清單（處理過的修改／確認檔名）跨狀態保留，watch_inbox 靠它避免重複處理。"""
    inbox = brief.get("inbox_folder")
    if not (inbox and Path(inbox).exists()):
        return
    p = Path(inbox, "_狀態.txt")
    done = []
    if p.exists():
        for l in p.read_text(encoding="utf-8-sig", errors="replace").splitlines():
            if l.startswith(("已處理：", "已處理修改：")):
                done = [x for x in l.split("：", 1)[1].split("、") if x]
    done += [x for x in processed.split("、") if x and x not in done]
    lines = [l for l in lines if l] + (["已處理：" + "、".join(done)] if done else [])
    p.write_text("\n".join([f"狀態：{status}", f"時間：{datetime.datetime.now():%Y-%m-%d %H:%M}"] + lines), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--status", default="完成")
    ap.add_argument("--note", default="")
    ap.add_argument("--processed", default="", help="本次處理過的修改檔名（、分隔）")
    a = ap.parse_args()
    d = project_dirs(a.project)
    brief = read_json(d["script"] / "brief.json", {})
    if a.status != "完成":
        extra = (["台詞稿：看 _台詞稿.txt 與 _分鏡預覽.jpg",
                  "同意請放「確認」開頭的檔；要改請放「修改」開頭的語音或文字"] if a.status == "待審閱" else [])
        status_file(brief, a.status, [a.note] + extra + [f"專案：{a.project}"], a.processed)
        print(f"[deliver] 已標記 {a.status}")
        return
    tl = read_json(d["out"] / "timeline.json")
    qa = read_json(d["qa"] / "qa.json", {})
    src = Path(tl["final"])
    OUTBOX.mkdir(parents=True, exist_ok=True)
    stamp = f"{datetime.datetime.now():%m%d_%H%M}"
    dst = OUTBOX / f"{src.stem}_{stamp}{src.suffix}"
    shutil.copy2(src, dst)
    if src.with_suffix(".srt").exists():
        shutil.copy2(src.with_suffix(".srt"), dst.with_suffix(".srt"))
    lines = [f"成片：{dst.name}（在「成品」資料夾）", f"長度：{qa.get('duration', tl['total'])} 秒",
             f"QA：{qa.get('verdict', '未跑')}"] + [f"注意：{w}" for w in qa.get("warns", [])] + [
        "要修改：在這個資料夾放一段「修改」開頭的語音或文字檔（例如 修改1.m4a），改好的台詞會先送審。", f"專案：{a.project}"]
    status_file(brief, "完成", lines, a.processed)
    script = read_json(d["script"] / "script.json", {})
    (Path(a.project) / "HANDOFF.md").write_text(f"""# HANDOFF：{script.get('title', Path(a.project).name)}

更新：{datetime.datetime.now():%Y-%m-%d %H:%M}（phone-quick-cut 自動產生）

## 已確認
- 任務單：{brief.get('raw', '').strip()[:200] or '（無，全預設）'}
- 風格 {script.get('style')}｜比例 {script.get('ratio')}｜聲音 {script.get('voice')}｜腳本由 {script.get('_meta', {}).get('written_by', '?')} 寫
- 成片：`{src}`（{qa.get('duration')} 秒，QA {qa.get('verdict')}）；OneDrive 複本 `{dst}`

## 懸而未決
{chr(10).join('- ' + w for w in qa.get('warns', [])) or '- 無'}
- 業主尚未親耳試聽配樂與旁白

## 下一步
- 修改：收件匣子夾放「修改*.m4a／修改*.txt」，或手動
  `py -3 -X utf8 D:/secondbrain/Skills/phone-quick-cut/scripts/run_job.py --project "{a.project}" --revise "<要求>"`
""", encoding="utf-8")
    print(f"[deliver] 已放到 {dst}")


if __name__ == "__main__":
    main()
