# -*- coding: utf-8 -*-
"""產生關機備援用的 Colab notebook：colab/phone_quick_cut.ipynb。改任何 scripts/*.py 或 references/*.md 後重跑：
  py -3 -X utf8 make_colab_nb.py [--copy-to-gdrive]

設計（2026-11-15 手機實測後重寫）：手機瀏覽器一切到別的 App 就會和 Colab 斷線
（「await connected: disconnected」），逐格執行與 files.upload／files.download 都會卡住。所以：
- 全部步驟放在「一個」儲存格：按下執行後在雲端跑到底，手機斷線也不影響
- 素材從 Google 雲端硬碟資料夾讀、成果寫回同一個資料夾，不經手機上傳下載
- try/finally 一定執行 runtime.unassign()：成功或出錯都關機
- 台詞審閱：第一次跑「出台詞稿」→ 看 _台詞稿.txt → 改「階段」為「台詞已確認，合成」再跑一次
  （要改台詞：直接編輯雲端硬碟裡的 _script.json 的 narration，或改表單後重出台詞稿）
"""
import argparse
import base64
import json
import shutil
import zlib
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
EMBED = ["pqc_common.py", "intake.py", "analyze.py", "write_script.py", "build.py", "qa.py", "review.py"]
REFS = ["styles.md", "script-format.md"]
GDRIVE = Path(r"G:\我的雲端硬碟\Colab")

MAIN = r'''#@title 📱 手機快剪（填好表單 → 按左邊 ▶ 一次 → 可以關掉手機畫面）
雲端硬碟資料夾 = "手機快剪/收件匣/測試"  #@param {type:"string"}
階段 = "出台詞稿（先審）"  #@param ["出台詞稿（先審）", "台詞已確認，合成", "不審，直接合成"]
主題 = "朋友慶生與週末逛街"  #@param {type:"string"}
風格 = "溫馨"  #@param ["溫馨", "創意", "幽默", "知識", "藝術"]
長度秒數 = 60  #@param {type:"slider", min:15, max:180, step:5}
比例 = "9:16"  #@param ["9:16", "16:9", "1:1", "4:5"]
聲音 = "男"  #@param ["男", "女", "不要旁白"]
配樂 = True  #@param {type:"boolean"}
保留現場原音 = False  #@param {type:"boolean"}

import base64, json, os, pathlib, shutil, subprocess, sys, time, traceback, zlib
from google.colab import drive, runtime
drive.mount("/content/drive")  # 第一次會跳 Google 授權，按「允許」後再關掉畫面
SRC = pathlib.Path("/content/drive/MyDrive") / 雲端硬碟資料夾
LOG = SRC / "_colab_log.txt"
def log(msg):
    line = time.strftime("%H:%M:%S ") + str(msg)
    print(line)
    with open(LOG, "a", encoding="utf-8") as f: f.write(line + "\n")
def status(s, *more):
    (SRC / "_狀態.txt").write_text("\n".join([f"狀態：{s}", time.strftime("時間：%Y-%m-%d %H:%M（UTC）"), *more]), encoding="utf-8")
try:
    status("處理中（Colab）", f"階段：{階段}")
    log("安裝工具…")
    subprocess.run("apt-get -qq install -y fonts-noto-cjk > /dev/null; pip -q install edge-tts faster-whisper pillow-heif opencc-python-reimplemented scenedetect",
                   shell=True, check=True)
    B = "__BLOB__"
    for k, v in json.loads(zlib.decompress(base64.b64decode(B)).decode("utf-8")).items():
        p = pathlib.Path("/content/pqc/skill") / k; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(v, encoding="utf-8")
    os.environ.update(PQC_INBOX="/content/pqc/inbox", PQC_OUTBOX="/content/pqc/outbox", PQC_VIDEO="/content/pqc/projects")
    S = "/content/pqc/skill/scripts"
    def sh(*a, ok=(0,)):
        r = subprocess.run([sys.executable, "-X", "utf8", *a], cwd=S, capture_output=True, text=True)
        log(r.stdout[-1500:]); r.stderr.strip() and log(r.stderr[-1500:])
        if r.returncode not in ok: raise RuntimeError(f"{a[0]} 失敗")
        return r.stdout
    inbox = pathlib.Path("/content/pqc/inbox/job"); inbox.mkdir(parents=True, exist_ok=True)
    for f in SRC.iterdir():
        if f.is_file() and not f.name.startswith(("_", ".")) and f.suffix.lower() not in (".m4a", ".mp3", ".wav", ".txt"):
            shutil.copy(f, inbox / f.name)
    log(f"素材 {len(list(inbox.iterdir()))} 個")
    out = sh("intake.py", "--src", str(inbox))
    proj = pathlib.Path([l.split("=", 1)[1] for l in out.splitlines() if l.startswith("PROJECT=")][0])
    bp = proj / "01_查核與腳本" / "brief.json"
    b = json.loads(bp.read_text(encoding="utf-8"))
    b.update(theme=主題, style=風格, target_seconds=int(長度秒數), ratio=比例, music=bool(配樂),
             keep_original_audio=bool(保留現場原音), no_narration=(聲音 == "不要旁白"), inbox_folder=None,
             voice={"男": "zh-TW-YunJheNeural", "女": "zh-TW-HsiaoChenNeural"}.get(聲音, "zh-TW-YunJheNeural"), guessed=[])
    bp.write_text(json.dumps(b, ensure_ascii=False, indent=2), encoding="utf-8")
    sh("analyze.py", "--project", str(proj), "--no-speech")
    saved = SRC / "_script.json"
    sp = proj / "01_查核與腳本" / "script.json"
    if 階段.startswith("台詞已確認") and saved.exists():
        shutil.copy(saved, sp); log("沿用已審閱的台詞（_script.json）")
    else:
        # 在主程序裡跑（google.colab.ai 只在 notebook 核心內可用，子程序叫不到）
        import runpy
        sys.path.insert(0, S); sys.argv = ["write_script.py", "--project", str(proj), "--mode", "auto"]
        try: runpy.run_path(f"{S}/write_script.py", run_name="__main__")
        except SystemExit as e:
            if e.code not in (0, None): raise RuntimeError(f"寫腳本失敗：{e.code}")
        log("腳本：" + json.loads(sp.read_text(encoding="utf-8")).get("_meta", {}).get("written_by", "?"))
        shutil.copy(sp, saved)
    if 階段.startswith("出台詞稿"):
        txt = sh("review.py", "--project", str(proj))
        (SRC / "_台詞稿.txt").write_text(txt.split("\n[review]")[0], encoding="utf-8")
        shutil.copy(proj / "04_QA" / "分鏡預覽.jpg", SRC / "_分鏡預覽.jpg")
        status("待審閱（Colab）", "看 _台詞稿.txt 與 _分鏡預覽.jpg；沒問題就把「階段」改成「台詞已確認，合成」再按一次 ▶",
               "要改台詞：編輯 _script.json 裡的 narration，或改表單後重出台詞稿")
    else:
        out = sh("build.py", "--project", str(proj))
        final = pathlib.Path([l.split("=", 1)[1] for l in out.splitlines() if l.startswith("FINAL=")][0])
        sh("qa.py", "--project", str(proj), "--no-listen", ok=(0, 1))
        dst = SRC / "成品"; dst.mkdir(exist_ok=True)
        shutil.copy(final, dst / final.name)
        if final.with_suffix(".srt").exists(): shutil.copy(final.with_suffix(".srt"), dst / final.with_suffix(".srt").name)
        status("完成（Colab）", f"成片：成品/{final.name}")
    log("完成")
except Exception as e:
    log("❌ " + traceback.format_exc()[-1500:])
    try: status("失敗（Colab）", f"原因：{e}", "詳見 _colab_log.txt")
    except Exception: pass
finally:
    try: drive.flush_and_unmount()
    except Exception: pass
    print("10 秒後關閉雲端機器…")
    time.sleep(10)
    runtime.unassign()  # 成功或失敗都關機，不會一直扣運算單元
'''


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--copy-to-gdrive", action="store_true")
    a = ap.parse_args()
    bundle = {f"scripts/{f}": (SKILL / "scripts" / f).read_text(encoding="utf-8") for f in EMBED}
    bundle.update({f"references/{f}": (SKILL / "references" / f).read_text(encoding="utf-8") for f in REFS})
    blob = base64.b64encode(zlib.compress(json.dumps(bundle, ensure_ascii=False).encode("utf-8"), 9)).decode()
    intro = """# 📱 手機快剪（電腦關機時的雲端備援）

1. 把照片影片放進 Google 雲端硬碟的一個資料夾（例如 `手機快剪/收件匣/測試`）。
2. 填下面表單，按儲存格左邊的 ▶ **一次**。第一次會跳 Google 授權，按「允許」。
3. 之後可以關掉手機畫面；雲端會自己跑完、**自己關機**。進度看該資料夾的 `_狀態.txt`。
4. 預設先出台詞稿：看 `_台詞稿.txt`、`_分鏡預覽.jpg`，沒問題把「階段」改成「台詞已確認，合成」再按一次 ▶。
5. 成片在該資料夾的 `成品/`。

> 不需要 GPU，用預設 CPU 執行階段即可。請勿放病人、病歷或他人隱私畫面。
"""
    nb = {"cells": [{"cell_type": "markdown", "metadata": {}, "source": intro},
                    {"cell_type": "code", "metadata": {"cellView": "form"}, "execution_count": None, "outputs": [],
                     "source": MAIN.replace("__BLOB__", blob)}],
          "metadata": {"colab": {"provenance": []}, "kernelspec": {"name": "python3", "display_name": "Python 3"},
                       "language_info": {"name": "python"}}, "nbformat": 4, "nbformat_minor": 0}
    out = SKILL / "colab" / "phone_quick_cut.ipynb"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(nb, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"已產生 {out}（單一儲存格，內嵌 {len(bundle)} 個檔）")
    if a.copy_to_gdrive and GDRIVE.exists():
        shutil.copy(out, GDRIVE / out.name)
        print(f"已複製到 {GDRIVE / out.name}")


if __name__ == "__main__":
    main()
