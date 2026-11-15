# -*- coding: utf-8 -*-
"""掃一次 OneDrive 收件匣，把「準備好」的子夾交給 run_job.py。給 Windows 工作排程器每 5 分鐘呼叫。

  py -3 -X utf8 watch_inbox.py --once [--agent claude|codex] [--dry-run]

準備好的條件：
  新片 ─ 子夾裡有照片／影片，且有任務單（語音備忘或 任務.txt），沒有 _狀態.txt，
         而且「檔案數＋總大小」連續 --settle 秒（預設 120）沒變（手機上傳會保留原始時間，不能看 mtime）
  送審 ─ 新片與修改都先停在「狀態：待審閱」（_台詞稿.txt＋_分鏡預覽.jpg），不直接合成
  確認 ─「待審閱」時出現「確認*／OK*／同意*」檔（語音、文字皆可）→ 合成、QA、交付
  修改 ─「待審閱」或「完成」時出現「修改*」語音或文字 → 改台詞後再送審
  已處理過的檔名記在 _狀態.txt「已處理：」，不會重複處理
  要重跑失敗的片：刪掉該夾的 _狀態.txt。
同時間只跑一件（收件匣根目錄 .pqc.lock，超過 3 小時視為殘留）。紀錄寫到收件匣根目錄 _pqc_log.txt。
"""
import argparse
import datetime
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from intake import brief_text, classify  # noqa: E402
from pqc_common import INBOX  # noqa: E402


def status_of(folder):
    p = folder / "_狀態.txt"
    if not p.exists():
        return None, {}
    lines = p.read_text(encoding="utf-8-sig", errors="replace").splitlines()
    kv = dict(l.split("：", 1) for l in lines if "：" in l)
    return kv.get("狀態"), {**kv, "_mtime": p.stat().st_mtime}


def settled(folder, settle, seen):
    """手機上傳常保留原始拍攝時間，不能看 mtime：改看「檔案數＋總大小」連續 settle 秒不變。"""
    files = [f for f in folder.iterdir() if f.is_file() and not f.name.startswith(("_", "."))]
    sig = f"{len(files)}:{sum(f.stat().st_size for f in files)}"
    prev = seen.get(folder.name)
    if not prev or prev[0] != sig:
        seen[folder.name] = [sig, time.time()]
        return False
    return time.time() - prev[1] >= settle


def log(msg):
    line = f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S} {msg}"
    print(line)
    with open(INBOX / "_pqc_log.txt", "a", encoding="utf-8") as f:
        f.write(line + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--agent", default=os.environ.get("PQC_AGENT", "claude"))
    ap.add_argument("--settle", type=int, default=120)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    if not INBOX.exists():
        INBOX.mkdir(parents=True)
        print(f"已建立收件匣 {INBOX}")
        return
    lock = INBOX / ".pqc.lock"
    if lock.exists() and time.time() - lock.stat().st_mtime < 3 * 3600:
        print("另一件還在跑，略過")
        return
    seen_p = INBOX / ".pqc_seen.json"
    seen = json.loads(seen_p.read_text(encoding="utf-8")) if seen_p.exists() else {}
    todo = None
    for folder in sorted(p for p in INBOX.iterdir() if p.is_dir() and not p.name.startswith(("_", "."))):
        media, briefs, revises, approves = classify(folder, with_approvals=True)
        st, kv = status_of(folder)
        ok = settled(folder, a.settle, seen)
        if todo:
            continue
        if st is None and media and briefs and ok:
            todo = (folder, ["--src", str(folder)])
        elif st in ("待審閱", "完成") and kv.get("專案") and ok:
            done = {x.strip() for x in (kv.get("已處理") or kv.get("已處理修改", "")).split("、") if x.strip()}
            new_rev = [r for r in revises if r.name not in done]
            new_ok = [r for r in approves if r.name not in done]
            proj = kv["專案"].strip()
            if new_rev:  # 有修改就先改台詞再送審（確認檔一併記為已處理，避免用舊台詞合成）
                todo = (folder, ["--project", proj, "--revise", brief_text(new_rev),
                                 "--processed", "、".join(r.name for r in new_rev + new_ok)])
            elif new_ok and st == "待審閱":
                todo = (folder, ["--project", proj, "--approve", "--processed", "、".join(r.name for r in new_ok)])
    seen_p.write_text(json.dumps(seen, ensure_ascii=False), encoding="utf-8")
    if todo:
        folder, job = todo
        log(f"開工：{folder.name} {' '.join(job[:1])}")
        if a.dry_run:
            print("  dry-run：", job)
            return
        lock.write_text(str(os.getpid()), encoding="utf-8")
        try:  # 一次只做一件，下一輪排程再接下一件
            r = subprocess.run([sys.executable, "-X", "utf8", str(HERE / "run_job.py"), *job, "--agent", a.agent],
                               capture_output=True, text=True, encoding="utf-8", errors="replace")
            (folder / "_pqc_run.log").write_text(r.stdout + "\n---\n" + r.stderr, encoding="utf-8")
            log(f"{'完成' if r.returncode == 0 else '失敗'}：{folder.name}")
        finally:
            lock.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
