# -*- coding: utf-8 -*-
"""寫（或修改）script.json。三種模式，依可用性由上往下退：

  agent     ：本機無頭呼叫 Claude Code 或 Codex，讓它「看」接觸表、讀 brief 後寫腳本（品質最好）
  llm       ：只送文字（任務單、拍攝時間、現場講話逐字稿，不送照片）給 LLM 寫腳本；Colab 用這個
  template  ：不靠 AI，依分數與時間順序自動排片，只有開頭與結尾旁白（保底）

  py -3 -X utf8 write_script.py --project <專案> --mode agent --agent claude
  py -3 -X utf8 write_script.py --project <專案> --mode agent --agent codex --revise "第二段太長，音樂換輕快"
"""
import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from pqc_common import MAX_SECONDS, ON_COLAB, find_agent, project_dirs, read_json, write_json

SKILL = Path(__file__).resolve().parents[1]
MUSIC = {"創意": "upbeat quirky indie pop, plucky synths, claps, 110 bpm",
         "溫馨": "warm acoustic guitar and soft piano, gentle, heartfelt, 80 bpm",
         "幽默": "playful comedic pizzicato, light percussion, bouncy, 120 bpm",
         "知識": "light ambient, soft marimba and pads, curious, 95 bpm",
         "藝術": "ambient cinematic, slow evolving pads, felt piano, minimal, 60 bpm"}
OPEN = {"創意": "先別急著滑走，", "溫馨": "這一天，想好好記下來。", "幽默": "本來以為是個平凡的一天，",
        "知識": "你知道嗎？", "藝術": ""}
CLOSE = {"創意": "下次，換你出發。", "溫馨": "謝謝這一天，我們都在。", "幽默": "嗯，至少照片很好看。",
         "知識": "下次來，記得多看一眼。", "藝術": ""}


def validate(script, index, brief):
    ids = {c["id"]: c for c in index["candidates"]}
    errs = []
    for k in ("title", "style", "ratio", "voice", "shots"):
        if k not in script:
            errs.append(f"缺欄位 {k}")
    for i, s in enumerate(script.get("shots", []), 1):
        if s.get("cand") not in ids:
            errs.append(f"第 {i} 鏡的 cand {s.get('cand')} 不在 media_index.json")
    est = sum(max(s.get("dur", ids.get(s.get("cand"), {}).get("dur", 3)), len(s.get("narration", "")) / 4.2 + 0.6)
              for s in script.get("shots", []))
    limit = min(MAX_SECONDS, brief.get("target_seconds", 90) * 1.1)
    if est > limit:
        errs.append(f"估計長度 {est:.0f} 秒超過上限 {limit:.0f} 秒")
    return errs, est


def agent_prompt(d, brief, revise):
    base = (f"你在執行技能 phone-quick-cut 的「寫腳本」步驟。專案夾：{d['script'].parent}\n"
            f"1. 讀 {SKILL / 'references' / 'styles.md'} 與 {SKILL / 'references' / 'script-format.md'}。\n"
            f"2. 讀 {d['script'] / 'brief.json'}（任務單）與 {d['media'] / 'media_index.json'}（候選片段）。\n"
            f"3. 看接觸表圖片：{', '.join(read_json(d['media'] / 'media_index.json')['contact_sheets'])}。\n"
            f"4. 依風格「{brief['style']}」、目標 {brief['target_seconds']} 秒、比例 {brief['ratio']}，"
            f"把完整的 script.json 寫到 {d['script'] / 'script.json'}（UTF-8）。只寫這個檔，不要執行其他程式、不要改其他檔案。\n"
            "旁白用繁體中文台灣用語，只描述看得到或任務單說過的事，不編造人名地名。")
    if revise:
        base += (f"\n\n這是修改：既有 {d['script'] / 'script.json'} 已存在，請讀它，依下列要求修改後覆寫同一檔：\n「{revise}」")
    return base


def run_agent(agent, d, brief, revise):
    exe = find_agent(agent)
    if not exe:
        raise RuntimeError(f"找不到 {agent} 執行檔")
    prompt = agent_prompt(d, brief, revise)
    proj = str(d["script"].parent)
    if agent == "claude":
        cmd = [exe, "-p", prompt, "--allowedTools", "Read", "Write", "Edit", "Glob",
               "--permission-mode", "acceptEdits", "--add-dir", proj, str(SKILL)]
    else:
        sheets = read_json(d["media"] / "media_index.json")["contact_sheets"]
        cmd = [exe, "exec", "--skip-git-repo-check", "--sandbox", "workspace-write", "--cd", proj, "--ephemeral"]
        for s in sheets:
            cmd += ["-i", s]
        cmd += ["--", prompt]
    print(f"[script] 呼叫 {agent} 無頭模式寫腳本 …")
    r = subprocess.run(cmd, cwd=proj, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=1200)
    (d["qa"] / f"agent_{agent}_log.txt").write_text((r.stdout or "") + "\n---stderr---\n" + (r.stderr or ""), encoding="utf-8")
    if r.returncode:
        raise RuntimeError(f"{agent} 回傳 {r.returncode}：{(r.stderr or r.stdout)[-400:]}")


def llm_complete(prompt):
    if ON_COLAB:
        try:
            from google.colab import ai  # Colab 內建、免金鑰
            return ai.generate_text(prompt)
        except Exception:
            pass
        try:
            from google.colab import userdata
            os.environ.setdefault("OPENROUTER_API_KEY", userdata.get("OPENROUTER_API_KEY"))
        except Exception:
            pass
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key and os.name == "nt":
        key = subprocess.run(["powershell", "-NoProfile", "-Command",
                              '[Environment]::GetEnvironmentVariable("OPENROUTER_API_KEY","User")'],
                             capture_output=True, text=True).stdout.strip()
    if not key:
        raise RuntimeError("沒有可用的 LLM（無 Colab AI、無 OPENROUTER_API_KEY）")
    import requests
    r = requests.post("https://openrouter.ai/api/v1/chat/completions", timeout=300,
                      headers={"Authorization": f"Bearer {key}"},
                      json={"model": os.environ.get("PQC_LLM", "google/gemini-2.5-flash"),
                            "messages": [{"role": "user", "content": prompt}]})
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def run_llm(d, brief, index, revise):
    cands = [{k: c[k] for k in ("id", "kind", "dur", "time", "score", "weak", "speech_text", "file")} for c in index["candidates"]]
    prompt = ("你是短影片剪輯師。依下列風格說明與格式，輸出一個 script.json（只輸出 JSON，不要其他文字）。\n\n"
              + (SKILL / "references" / "styles.md").read_text(encoding="utf-8") + "\n\n"
              + (SKILL / "references" / "script-format.md").read_text(encoding="utf-8")
              + f"\n\n任務單：{json.dumps(brief, ensure_ascii=False)}\n候選片段（你看不到畫面，只能依檔名、時間、分數、現場講話判斷）："
              + json.dumps(cands, ensure_ascii=False))
    old = read_json(d["script"] / "script.json")
    if revise and old:
        prompt += f"\n\n既有腳本：{json.dumps(old, ensure_ascii=False)}\n請依此修改要求改寫：「{revise}」"
    txt = llm_complete(prompt)
    m = re.search(r"\{.*\}", txt, re.S)
    if not m:
        raise RuntimeError("LLM 沒回 JSON")
    write_json(d["script"] / "script.json", json.loads(m.group(0)))


def run_template(d, brief, index):
    st = brief["style"]
    good = [c for c in index["candidates"] if not c["weak"]] or index["candidates"]
    budget, shots, total = brief["target_seconds"] * 0.95, [], 0.0
    per = {"創意": 2.5, "幽默": 2.5, "知識": 4, "溫馨": 4.5, "藝術": 5.5}[st]
    if sum(min(c["dur"], per) for c in good) > budget:  # 太多就取分數高的，再依時間排回去
        keep = sorted(good, key=lambda c: -c["score"])
        chosen, acc = [], 0.0
        for c in keep:
            if acc + min(c["dur"], per) > budget:
                continue
            chosen.append(c)
            acc += min(c["dur"], per)
        good = sorted(chosen, key=lambda c: (c["time"], c["in"]))
    for c in good:
        dur = min(c["dur"], per) if c["kind"] == "video" else per
        if total + dur > budget:
            break
        shot = {"cand": c["id"], "dur": round(dur, 2), "narration": ""}
        if c.get("speech_text") and brief.get("keep_original_audio"):
            shot.update(keep_audio=True, dur=c["dur"])
        shots.append(shot)
        total += shot["dur"]
    if shots and not brief.get("no_narration"):
        shots[0]["narration"] = (OPEN[st] + brief["theme"] + "。").strip("，")
        shots[-1]["narration"] = shots[-1]["narration"] or CLOSE[st]
    write_json(d["script"] / "script.json", {
        "title": brief["theme"], "style": st, "ratio": brief["ratio"], "voice": brief["voice"], "rate": "+0%",
        "fade": "soft" if st in ("溫馨", "藝術") else "none",
        "music": {"enabled": brief.get("music", True), "prompt": MUSIC[st], "provider": "auto"},
        "shots": shots, "outro": ""})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--mode", choices=["agent", "llm", "template", "auto"], default="auto")
    ap.add_argument("--agent", choices=["claude", "codex"], default=os.environ.get("PQC_AGENT", "claude"))
    ap.add_argument("--revise", help="修改要求（文字）")
    a = ap.parse_args()
    d = project_dirs(a.project)
    brief = read_json(d["script"] / "brief.json")
    index = read_json(d["media"] / "media_index.json")
    order = {"auto": ["llm", "template"] if ON_COLAB else ["agent", "llm", "template"]}.get(a.mode, [a.mode])
    if a.mode == "auto" and not ON_COLAB:
        order = ["agent", "agent2", "llm", "template"]
    other = "codex" if a.agent == "claude" else "claude"
    for mode in order:
        try:
            if mode == "agent":
                run_agent(a.agent, d, brief, a.revise)
            elif mode == "agent2":
                run_agent(other, d, brief, a.revise)
            elif mode == "llm":
                run_llm(d, brief, index, a.revise)
            else:
                if a.revise:
                    raise RuntimeError("template 模式無法依文字修改")
                run_template(d, brief, index)
            script = read_json(d["script"] / "script.json")
            errs, est = validate(script, index, brief)
            if errs:
                raise RuntimeError("；".join(errs))
            script.setdefault("_meta", {})["written_by"] = {"agent": a.agent, "agent2": other}.get(mode, mode)
            write_json(d["script"] / "script.json", script)
            print(f"[script] 完成（{script['_meta']['written_by']}），{len(script['shots'])} 鏡，估計 {est:.0f} 秒")
            return
        except Exception as e:
            print(f"[script] {mode} 失敗：{e}", file=sys.stderr)
    sys.exit("[script] 所有模式都失敗")


if __name__ == "__main__":
    main()
