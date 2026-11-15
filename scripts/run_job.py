# -*- coding: utf-8 -*-
"""一鍵跑管線。預設有「台詞審閱」關卡：寫完腳本先送審，業主確認後才合成。

  新片：   run_job.py --src "E:\\OneDrive\\手機快剪\\收件匣\\陽明山"        → intake、analyze、腳本、送審（狀態：待審閱）
  改台詞： run_job.py --project <專案> --revise "第3句改成…"              → 改腳本、再送審
  確認後： run_job.py --project <專案> --approve                          → 合成、QA、交付（狀態：完成）
  不審閱： 加 --no-review（或環境變數 PQC_REVIEW=0），一路做到交付
  其他：   --agent claude|codex（寫腳本的 agent）、--mode agent|llm|template|auto、--draft、
           --processed "檔名、檔名"（這次處理的修改／確認檔，記進 _狀態.txt 避免重複）

任何一步失敗都會在收件匣子夾寫「_狀態.txt：失敗」並附原因，手機上看得到。
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from pqc_common import read_json  # noqa: E402

PROCESSED = ""


def deliver(project, status, note=""):
    subprocess.run([sys.executable, "-X", "utf8", str(HERE / "deliver.py"), "--project", project, "--status", status,
                    "--note", note, "--processed", PROCESSED])


def step(name, args, project=None):
    print(f"\n===== {name} =====", flush=True)
    r = subprocess.run([sys.executable, "-X", "utf8", str(HERE / f"{name}.py")] + args, capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    print(r.stdout, end="")
    if r.stderr.strip():
        print(r.stderr[-2000:], end="", file=sys.stderr)
    if r.returncode and not (name == "qa" and r.returncode == 1):
        if project:
            deliver(project, "失敗", f"{name} 失敗：{(r.stderr or r.stdout)[-300:]}")
        sys.exit(f"[run_job] {name} 失敗")
    return r


def main():
    global PROCESSED
    ap = argparse.ArgumentParser()
    ap.add_argument("--src")
    ap.add_argument("--project")
    ap.add_argument("--revise")
    ap.add_argument("--approve", action="store_true", help="台詞已確認，直接合成交付")
    ap.add_argument("--processed", "--revise-files", dest="processed", default="")
    ap.add_argument("--no-review", action="store_true")
    ap.add_argument("--agent", default=os.environ.get("PQC_AGENT", "claude"), choices=["claude", "codex"])
    ap.add_argument("--mode", default="auto")
    ap.add_argument("--draft", action="store_true")
    ap.add_argument("--no-speech", action="store_true")
    a = ap.parse_args()
    PROCESSED = a.processed
    review = not a.no_review and os.environ.get("PQC_REVIEW", "1") != "0"
    if not (a.src or a.project):
        ap.error("需要 --src 或 --project")
    proj = a.project
    if a.src and not proj:
        out = step("intake", ["--src", a.src]).stdout
        proj = next(l.split("=", 1)[1] for l in out.splitlines() if l.startswith("PROJECT="))
        brief = read_json(Path(proj) / "01_查核與腳本" / "brief.json")
        deliver(proj, "處理中", f"主題 {brief['theme']}｜{brief['style']}｜{brief['target_seconds']} 秒｜{brief['ratio']}")
        step("analyze", ["--project", proj] + (["--no-speech"] if a.no_speech else []), proj)
    if not a.approve:
        ws = ["--project", proj, "--mode", a.mode, "--agent", a.agent] + (["--revise", a.revise] if a.revise else [])
        step("write_script", ws, proj)
        if review:
            step("review", ["--project", proj], proj)
            deliver(proj, "待審閱", "台詞稿已產生，等你確認")
            print(f"\n[run_job] 待審閱：{proj}")
            return
    step("build", ["--project", proj] + (["--draft"] if a.draft else []), proj)
    qa = step("qa", ["--project", proj], proj)
    if qa.returncode == 1:
        deliver(proj, "失敗", "QA 未通過，詳見 04_QA\\qa.json")
        sys.exit("[run_job] QA FAIL")
    step("deliver", ["--project", proj, "--processed", PROCESSED], proj)
    print(f"\n[run_job] 全部完成：{proj}")


if __name__ == "__main__":
    main()
