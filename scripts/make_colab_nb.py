# -*- coding: utf-8 -*-
"""產生關機備援用的 Colab notebook：colab/phone_quick_cut.ipynb。改任何 scripts/*.py 或 references/*.md 後重跑：
  python -X utf8 make_colab_nb.py [--check] [--copy-to <自己的 Drive 資料夾>]

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
EMBED = ["pqc_common.py", "intake.py", "analyze.py", "write_script.py", "build.py", "qa.py", "review.py", "lyria_bgm.py"]
REFS = ["styles.md", "script-format.md"]

MAIN = r'''#@title 📱 手機快剪（填好表單 → 按左邊 ▶ 一次 → 可以關掉手機畫面）
雲端硬碟資料夾 = "手機快剪/收件匣/測試"  #@param {type:"string"}
階段 = "出台詞稿（先審）"  #@param ["出台詞稿（先審）", "重送目前稿（不重寫）", "台詞已確認，合成"]
主題 = "生活紀錄"  #@param {type:"string"}
風格 = "溫馨"  #@param ["溫馨", "創意", "幽默", "知識", "藝術"]
長度秒數 = 60  #@param {type:"slider", min:15, max:180, step:5}
比例 = "9:16"  #@param ["9:16", "16:9", "1:1", "4:5"]
聲音 = "男"  #@param ["男", "女", "不要旁白"]
配樂 = True  #@param {type:"boolean"}
保留現場原音 = False  #@param {type:"boolean"}
允許文字雲端 = False  #@param {type:"boolean"}
配樂來源 = "synth"  #@param ["synth", "musicgen"]

import base64, hashlib, json, os, pathlib, shutil, subprocess, sys, time, traceback, zlib
from google.colab import drive, runtime
SRC = None
mounted = False
def log(msg):
    line = time.strftime("%H:%M:%S ") + str(msg)
    print(line)
    if SRC is not None and SRC.is_dir():
        try:
            with open(SRC / "_colab_log.txt", "a", encoding="utf-8") as f: f.write(line + "\n")
        except OSError: pass
def status(s, *more):
    stamp = "時間：" + time.strftime("%Y-%m-%d %H:%M") + "（UTC）"
    (SRC / "_狀態.txt").write_text("\n".join([f"狀態：{s}", stamp, *more]), encoding="utf-8")
try:
    drive.mount("/content/drive")
    mounted = True
    root = pathlib.Path("/content/drive/MyDrive").resolve()
    source = (root / 雲端硬碟資料夾).resolve()
    if not source.is_relative_to(root) or not source.is_dir():
        raise ValueError("素材資料夾不存在或不在 MyDrive 內；請先建立資料夾並上傳素材")
    SRC = source
    status("處理中（Colab）", f"階段：{階段}")
    log("安裝工具…")
    subprocess.run(["apt-get", "-qq", "update"], check=True)
    subprocess.run(["apt-get", "-qq", "install", "-y", "ffmpeg", "fonts-noto-cjk"], check=True)
    B = "__BLOB__"
    for k, v in json.loads(zlib.decompress(base64.b64decode(B)).decode("utf-8")).items():
        p = pathlib.Path("/content/pqc/skill") / k; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(v, encoding="utf-8")
    subprocess.run([sys.executable, "-m", "pip", "-q", "install", "-r", "/content/pqc/skill/requirements.txt"], check=True)
    if 配樂 and 配樂來源 == "musicgen":
        subprocess.run([sys.executable, "-m", "pip", "-q", "install", "-r", "/content/pqc/skill/requirements-musicgen.txt"], check=True)
    os.environ.update(PQC_INBOX="/content/pqc/inbox", PQC_OUTBOX="/content/pqc/outbox", PQC_VIDEO="/content/pqc/projects",
                      PQC_ALLOW_CLOUD="1" if 允許文字雲端 else "0", PQC_ALLOW_PAID_MUSIC="0")
    S = "/content/pqc/skill/scripts"
    def sh(*a):
        r = subprocess.run([sys.executable, "-X", "utf8", *a], cwd=S, capture_output=True, text=True, encoding="utf-8", errors="replace")
        log(r.stdout[-1500:]); r.stderr.strip() and log(r.stderr[-1500:])
        if r.returncode: raise RuntimeError(f"{a[0]} 失敗")
        return r.stdout
    inbox = pathlib.Path("/content/pqc/inbox/job"); inbox.mkdir(parents=True, exist_ok=True)
    from importlib import invalidate_caches
    sys.path.insert(0, S)
    from pqc_common import VIDEO_EXT, PHOTO_EXT
    manifest = {}
    for f in sorted(SRC.iterdir()):
        if f.is_file() and not f.name.startswith(("_", ".")) and f.suffix.lower() in VIDEO_EXT | PHOTO_EXT:
            digest = hashlib.sha256()
            with f.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""): digest.update(chunk)
            manifest[f.name] = digest.hexdigest()
            shutil.copy2(f, inbox / f.name)
    if not manifest: raise ValueError("素材夾沒有可用的照片或影片")
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
    saved_manifest = SRC / "_source_manifest.json"
    saved_review = SRC / "_review.json"
    settings = {"theme":主題, "style":風格, "seconds":int(長度秒數), "ratio":比例, "voice":聲音,
                "music":bool(配樂), "provider":配樂來源, "keep_audio":bool(保留現場原音)}
    sp = proj / "01_查核與腳本" / "script.json"
    if 階段.startswith(("台詞已確認", "重送目前稿")):
        if not saved.exists() or not saved_manifest.exists():
            raise ValueError("沒有已送審稿；請先執行「出台詞稿」")
        if json.loads(saved_manifest.read_text(encoding="utf-8")) != manifest:
            raise ValueError("素材在送審後已變更；請重新出台詞稿並確認")
        shutil.copy(saved, sp); log("沿用已審閱的台詞（_script.json）")
    else:
        # 在主程序裡跑（google.colab.ai 只在 notebook 核心內可用，子程序叫不到）
        import runpy
        sys.path.insert(0, S); sys.argv = ["write_script.py", "--project", str(proj), "--mode", "auto"]
        try: runpy.run_path(f"{S}/write_script.py", run_name="__main__")
        except SystemExit as e:
            if e.code not in (0, None): raise RuntimeError(f"寫腳本失敗：{e.code}")
        log("腳本：" + json.loads(sp.read_text(encoding="utf-8")).get("_meta", {}).get("written_by", "?"))
    # New runtime must validate the saved script against this run's candidates and brief.
    script = json.loads(sp.read_text(encoding="utf-8"))
    script.setdefault("music", {})["provider"] = 配樂來源
    script["music"]["enabled"] = bool(配樂)
    sp.write_text(json.dumps(script, ensure_ascii=False, indent=2), encoding="utf-8")
    sh("write_script.py", "--project", str(proj), "--validate-only")
    if not 階段.startswith("台詞已確認"):
        txt = sh("review.py", "--project", str(proj))
        (SRC / "_台詞稿.txt").write_text(txt.split("\n[review]")[0], encoding="utf-8")
        shutil.copy(proj / "04_QA" / "分鏡預覽.jpg", SRC / "_分鏡預覽.jpg")
        shutil.copy(sp, saved)
        saved_manifest.write_text(json.dumps(manifest, ensure_ascii=False, sort_keys=True), encoding="utf-8")
        saved_review.write_text(json.dumps({"script_sha256":hashlib.sha256(sp.read_bytes()).hexdigest(), "settings":settings},
                                           ensure_ascii=False, sort_keys=True), encoding="utf-8")
        status("待審閱（Colab）", "看 _台詞稿.txt 與 _分鏡預覽.jpg；沒問題就把「階段」改成「台詞已確認，合成」再按一次 ▶",
               "要改台詞：編輯 _script.json 裡的 narration，再選「重送目前稿（不重寫）」取得新版預覽")
    else:
        if not saved_review.exists(): raise ValueError("缺少送審紀錄；請先選「重送目前稿（不重寫）」")
        reviewed = json.loads(saved_review.read_text(encoding="utf-8"))
        if reviewed.get("script_sha256") != hashlib.sha256(sp.read_bytes()).hexdigest() or reviewed.get("settings") != settings:
            raise ValueError("腳本或表單在送審後已變更；請選「重送目前稿（不重寫）」並重新確認")
        out = sh("build.py", "--project", str(proj))
        final = pathlib.Path([l.split("=", 1)[1] for l in out.splitlines() if l.startswith("FINAL=")][0])
        sh("qa.py", "--project", str(proj), "--no-listen")
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
    if mounted:
        try: drive.flush_and_unmount()
        except Exception: pass
    print("10 秒後關閉雲端機器…")
    time.sleep(10)
    runtime.unassign()  # 成功或失敗都關機，不會一直扣運算單元
'''


def build_notebook():
    bundle = {f"scripts/{f}": (SKILL / "scripts" / f).read_text(encoding="utf-8") for f in EMBED}
    bundle.update({f"references/{f}": (SKILL / "references" / f).read_text(encoding="utf-8") for f in REFS})
    for name in ("requirements.txt", "requirements-musicgen.txt", "assets/pronunciation_zh.json"):
        bundle[name] = (SKILL / name).read_text(encoding="utf-8")
    blob = base64.b64encode(zlib.compress(json.dumps(bundle, ensure_ascii=False, sort_keys=True).encode("utf-8"), 9)).decode()
    intro = """# 📱 手機快剪（電腦關機時的雲端備援）

把照片影片放到自己 Google 雲端硬碟的資料夾，填表後先執行「出台詞稿」。確認台詞與分鏡後，再選「台詞已確認，合成」。每次執行都會嘗試卸載 Drive 並關閉 runtime；仍須從 Colab 管理工作階段確認已關機。

預設 CPU、模板寫稿與本機合成配樂。只有勾選「允許文字雲端」才會傳送任務單、檔名與逐字稿給 Colab AI／OpenRouter；請勿放病人或未經授權的私人影像。Edge-TTS 會傳送旁白文字。第一次掛載須完成 Google 授權；Colab 配額、逾時或強制中止仍可能影響執行。
"""
    return {"cells": [{"cell_type": "markdown", "metadata": {}, "source": intro},
                       {"cell_type": "code", "metadata": {"cellView": "form"}, "execution_count": None,
                        "outputs": [], "source": MAIN.replace("__BLOB__", blob)}],
            "metadata": {"colab": {"provenance": []}, "kernelspec": {"name": "python3", "display_name": "Python 3"},
                         "language_info": {"name": "python"}}, "nbformat": 4, "nbformat_minor": 0}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="只檢查 notebook 是否與來源一致，不改檔")
    ap.add_argument("--copy-to", type=Path, help="複製 notebook 到指定資料夾（例如自己的 Google Drive）")
    a = ap.parse_args()
    nb = build_notebook()
    out = SKILL / "colab" / "phone_quick_cut.ipynb"
    content = json.dumps(nb, ensure_ascii=False, indent=1) + "\n"
    if a.check:
        if not out.exists() or out.read_text(encoding="utf-8") != content:
            raise SystemExit("notebook 與來源不同，請執行 scripts/make_colab_nb.py 後提交")
        print("[notebook] 內嵌檔案與來源一致")
        return
    out.parent.mkdir(exist_ok=True)
    out.write_text(content, encoding="utf-8", newline="\n")
    print(f"已產生 {out}（單一儲存格）")
    if a.copy_to:
        a.copy_to.mkdir(parents=True, exist_ok=True)
        shutil.copy(out, a.copy_to / out.name)
        print(f"已複製到 {a.copy_to / out.name}")


if __name__ == "__main__":
    main()
