# -*- coding: utf-8 -*-
"""script.json → 配音、字幕、音樂、合成成片。

  py -3 -X utf8 build.py --project <專案> [--draft] [--name 片名]

--draft：半解析度、快速編碼（約快 4 倍），給業主先看；不加就是 1080 定稿。
流程：逐句 Edge-TTS（有快取）→ 排時間軸（旁白比鏡頭長就拉長鏡頭）→ 逐鏡算圖（照片 Ken Burns、
比例不合用模糊背景）→ 串接 → 旁白＋現場聲＋音樂（說話時自動壓低）→ 響度 -16 LUFS → 燒字幕。
"""
import argparse
import hashlib
import math
import os
import shutil
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np

from pqc_common import (FPS, MAX_SECONDS, ON_COLAB, RATIOS, api_key, apply_pron, duration, edge_tts_cmd,
                        env_enabled, find_font_path, font_family, project_dirs, read_json, run, safe_name, write_json)

SR = 48000
LEAD = 0.25          # 旁白在鏡頭開始後多久開口
TAIL = 0.45          # 旁白結束後鏡頭至少再停多久
MAX_FREEZE = 2.0     # 超過此值就要求縮短台詞／鏡頭，絕不跨剪接點
LYRIA = Path(__file__).resolve().parent / "lyria_bgm.py"


# ---------- 配音 ----------
class TTSFail(Exception):
    pass


def tts(text, voice, rate, out_dir):
    say = apply_pron(text)
    h = hashlib.md5(f"{voice}|{rate}|{say}".encode()).hexdigest()[:12]
    mp3 = out_dir / f"{h}.mp3"
    if not (mp3.exists() and mp3.stat().st_size > 0):
        for attempt in range(3):  # 微軟端偶發 NoAudioReceived，重試即可
            r = subprocess.run(edge_tts_cmd() + ["--voice", voice, f"--rate={rate}", "--text", say, "--write-media", str(mp3)],
                               capture_output=True, text=True, encoding="utf-8", errors="replace")
            if r.returncode == 0 and mp3.exists() and mp3.stat().st_size > 0:
                break
            __import__("time").sleep(2 + 3 * attempt)
        if r.returncode or not mp3.exists() or mp3.stat().st_size == 0:
            mp3.unlink(missing_ok=True)
            hint = "（403 多半是 edge-tts 太舊：uv tool upgrade edge-tts）" if "403" in r.stderr else ""
            raise TTSFail(f"Edge-TTS 失敗{hint}：{voice}｜{text}\n{r.stderr[-300:]}")
    pcm = np.frombuffer(run(["ffmpeg", "-v", "error", "-i", mp3, "-ac", "1", "-ar", SR, "-f", "s16le", "-"],
                            text=False, encoding=None, errors=None).stdout, np.int16)
    return trim(pcm)


def trim(pcm, thr_db=-45.0):
    hop = SR // 100
    n = len(pcm) // hop
    if n == 0:
        return pcm
    fr = pcm[: n * hop].astype(np.float64).reshape(n, hop)
    db = 20 * np.log10(np.sqrt((fr ** 2).mean(1)) + 1e-9) - 90.3
    v = np.where(db > thr_db)[0]
    if not len(v):
        return pcm
    return pcm[max(0, v[0] * hop - SR // 20): min(len(pcm), (v[-1] + 1) * hop + SR // 20)]


def write_wav(path, pcm):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.astype(np.int16).tobytes())


# ---------- 時間軸 ----------
def plan(script, cands, tts_dir):
    shots, t = [], 0.0
    for i, s in enumerate(script["shots"], 1):
        c = cands[s["cand"]]
        sh = {"i": i, "cand": c, "in": float(s.get("in", c["in"])), "want": float(s.get("dur", c["dur"])),
              "narration": s.get("narration", "").strip(), "caption": s.get("caption", ""),
              "speech_caption": s.get("speech_caption", ""),
              "keep_audio": bool(s.get("keep_audio", bool(c.get("speech_text")) and not s.get("narration")))}
        sh["voice"] = tts(sh["narration"], script["voice"], script.get("rate", "+0%"), tts_dir) if sh["narration"] else None
        vlen = len(sh["voice"]) / SR if sh["voice"] is not None else 0
        need = LEAD + vlen + TAIL if vlen else 0
        ln = max(sh["want"], need, 1.0)
        sh["freeze"] = 0.0
        if c["kind"] == "video":
            ss, se = c.get("scene") or (0.0, c["src_dur"])
            if not (ss <= sh["in"] < se):
                raise ValueError(f"第 {i} 鏡起點不在候選鏡頭 {ss:.2f}–{se:.2f} 秒內；請改選候選片段")
            # 借同一鏡頭的素材，之後最多停格兩秒；不擴大 scene 範圍。
            in_s = max(ss, se - ln) if ln > se - sh["in"] else sh["in"]
            if ln - (se - in_s) > MAX_FREEZE + 0.001:
                raise ValueError(f"第 {i} 鏡需 {ln:.2f} 秒，但同一鏡頭只有 {se - ss:.2f} 秒，"
                                 f"最多停格 {MAX_FREEZE:.0f} 秒；請縮短旁白／dur 或換較長候選")
            sh["in"] = in_s
            sh["freeze"] = max(0.0, ln - (se - in_s))
        sh["len"] = round(ln, 3)
        sh["start"] = round(t, 3)
        t += sh["len"]
        shots.append(sh)
    return shots, t


# ---------- 畫面 ----------
def shot_filter(sh, W, H, fade, last):
    c, ln = sh["cand"], sh["len"]
    ar_s, ar_t = c["w"] / c["h"], W / H
    cover = abs(ar_s / ar_t - 1) < 0.22
    if c["kind"] == "photo":
        frames = max(2, round(ln * FPS))
        SW, SH = W * 3 // 2 // 2 * 2, H * 3 // 2 // 2 * 2
        if cover:
            base = f"[0:v]scale={SW}:{SH}:force_original_aspect_ratio=increase,crop={SW}:{SH},setsar=1[c]"
        else:
            base = (f"[0:v]split[a][b];[a]scale={SW}:{SH}:force_original_aspect_ratio=increase,crop={SW}:{SH},"
                    f"boxblur=30:2,eq=brightness=-0.1[bg];[b]scale={SW}:{SH}:force_original_aspect_ratio=decrease[fg];"
                    f"[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1[c]")
        zin = sh["i"] % 2 == 1
        z = f"1+0.08*on/{frames}" if zin else f"1.08-0.08*on/{frames}"
        v = (base + f";[c]zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={W}x{H}:fps={FPS},"
             f"format=yuv420p")
    else:
        if cover:
            v = f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}"
        else:
            v = (f"[0:v]split[a][b];[a]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},boxblur=30:2,"
                 f"eq=brightness=-0.1[bg];[b]scale={W}:{H}:force_original_aspect_ratio=decrease[fg];"
                 f"[bg][fg]overlay=(W-w)/2:(H-h)/2")
        v += f",fps={FPS},setsar=1,format=yuv420p"
        if sh["freeze"] > 0:
            v += f",tpad=stop_mode=clone:stop_duration={sh['freeze']:.3f}"
    v += f",trim=duration={ln:.3f},setpts=PTS-STARTPTS"
    if fade == "soft":
        v += f",fade=in:st=0:d=0.25,fade=out:st={max(0, ln - 0.25):.3f}:d=0.25"
    elif last:
        v += f",fade=out:st={max(0, ln - 0.6):.3f}:d=0.6"
    return v + "[v]"


def render_shot(sh, W, H, fade, last, out, crf, preset):
    c, ln = sh["cand"], sh["len"]
    cmd = ["ffmpeg", "-v", "error", "-y"]
    if c["kind"] == "photo":
        cmd += ["-i", c["path"]]
    else:
        # Bound decode duration too: an extra 0.1s could leak the next scene into tpad.
        cmd += ["-ss", f"{sh['in']:.3f}", "-t", f"{ln - sh['freeze']:.3f}", "-i", c["path"]]
    cmd += ["-f", "lavfi", "-t", f"{ln:.3f}", "-i", f"anullsrc=r={SR}:cl=stereo"]
    fc = shot_filter(sh, W, H, fade, last)
    if sh["keep_audio"] and c["kind"] == "video" and c.get("has_audio"):
        fc += (f";[0:a]aresample={SR},aformat=channel_layouts=stereo,apad,atrim=duration={ln:.3f},"
               f"afade=in:d=0.08,afade=out:st={max(0, ln - 0.15):.3f}:d=0.15[a]")
    else:
        fc += ";[1:a]anull[a]"
    cmd += ["-filter_complex", fc, "-map", "[v]", "-map", "[a]", "-t", f"{ln:.3f}",
            "-c:v", "libx264", "-preset", preset, "-crf", str(crf), "-r", str(FPS),
            "-c:a", "aac", "-b:a", "160k", "-ar", str(SR), out]
    run(cmd)


# ---------- 音樂 ----------
def synth_music(path, seconds, style):
    """不靠網路的保底配樂：和弦襯底＋簡單琶音（numpy 合成）。"""
    bpm = {"創意": 110, "溫馨": 80, "幽默": 120, "知識": 95, "藝術": 60}.get(style, 85)
    prog = [[0, 4, 7], [-3, 0, 4], [-7, -3, 0], [-5, -1, 2]]  # I–vi–IV–V
    root, beat = 261.63 / 2, 60 / bpm
    n = int((seconds + 2) * SR)
    t = np.arange(n) / SR
    out = np.zeros(n)
    bar = beat * 4
    for k in range(int(math.ceil((seconds + 2) / bar))):
        chord = prog[k % 4]
        a, b = int(k * bar * SR), min(n, int((k + 1) * bar * SR))
        seg = t[a:b] - t[a]
        env = np.minimum(1, seg / 0.4) * np.minimum(1, (bar - seg) / 0.4)
        for semi in chord:
            f = root * 2 ** (semi / 12)
            out[a:b] += 0.12 * env * (np.sin(2 * np.pi * f * seg) + 0.3 * np.sin(4 * np.pi * f * seg))
        for j in range(8 if bpm >= 90 else 4):  # 琶音
            s0 = a + int(j * bar / (8 if bpm >= 90 else 4) * SR)
            if s0 >= n:
                break
            f = root * 4 * 2 ** (chord[j % 3] / 12)
            m = min(n - s0, int(0.6 * SR))
            st = np.arange(m) / SR
            out[s0:s0 + m] += 0.08 * np.sin(2 * np.pi * f * st) * np.exp(-st * 5)
    out = out / (np.abs(out).max() + 1e-9) * 0.6
    write_wav(path, (out * 32767).astype(np.int16))


def musicgen(path, seconds, prompt):
    import torch
    from transformers import AutoProcessor, MusicgenForConditionalGeneration
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    proc = AutoProcessor.from_pretrained("facebook/musicgen-small")
    model = MusicgenForConditionalGeneration.from_pretrained("facebook/musicgen-small").to(dev)
    seg = min(30, seconds)
    inp = proc(text=[prompt + ", instrumental"], padding=True, return_tensors="pt").to(dev)
    audio = model.generate(**inp, max_new_tokens=int(seg * 50))[0, 0].cpu().numpy()
    sr = model.config.audio_encoder.sampling_rate
    tmp = Path(path).with_suffix(".raw.wav")
    with wave.open(str(tmp), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes((np.clip(audio / (np.abs(audio).max() + 1e-9) * 0.8, -1, 1) * 32767).astype(np.int16).tobytes())
    run(["ffmpeg", "-v", "error", "-y", "-i", tmp, "-ar", SR, path])


def get_music(script, seconds, mdir):
    m = script.get("music", {})
    if not m.get("enabled", True):
        return None
    prompt = m.get("prompt") or "gentle acoustic background music"
    prov = m.get("provider", "auto")
    h = hashlib.md5(f"{prov}|{prompt}|{script.get('style')}|{seconds:.3f}".encode()).hexdigest()[:10]
    for ext in (".mp3", ".wav", "_synth.wav"):
        f = mdir / f"music_{h}{ext}"
        if f.exists() and f.stat().st_size > 0:
            return f
    if prov == "auto":
        tries = ["lyria", "synth"] if api_key() and env_enabled("PQC_ALLOW_PAID_MUSIC") else ["synth"]
    else:
        tries = [prov] + (["synth"] if prov != "synth" else [])
    if prov not in ("auto", "lyria", "musicgen", "synth"):
        raise ValueError(f"未知配樂 provider：{prov}")
    for p in tries:
        try:
            if p == "lyria":
                out = mdir / f"music_{h}.mp3"
                if not api_key() or not env_enabled("PQC_ALLOW_PAID_MUSIC"):
                    raise RuntimeError("Lyria 需金鑰及 PQC_ALLOW_PAID_MUSIC=1；改用本機配樂")
                r = subprocess.run([sys.executable, "-X", "utf8", str(LYRIA), "--prompt", prompt, "-o", str(out)],
                                   capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)
                if r.returncode:
                    raise RuntimeError(f"Lyria 未產出：{r.stderr[-160:]}")
                duration(out)  # Reject non-audio responses before caching them.
            elif p == "musicgen":
                out = mdir / f"music_{h}.wav"
                musicgen(out, seconds, prompt)
            else:
                out = mdir / f"music_{h}_synth.wav"
                synth_music(out, seconds, script.get("style"))
            if out.exists() and out.stat().st_size > 0:
                print(f"[build] 配樂：{p} → {out.name}")
                return out
        except (Exception, SystemExit) as e:
            print(f"[build] 配樂 {p} 失敗：{e}", file=sys.stderr)
    return None


# ---------- 字幕 ----------
def ass_time(s):
    s = max(0.0, s)
    return f"{int(s // 3600)}:{int(s % 3600 // 60):02d}:{s % 60:05.2f}"


def srt_time(s):
    ms = int(round(max(0.0, s) * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def split_lines(text, maxc):
    parts = [p for p in __import__("re").split(r"[，,。．.！!？?；;：:、\s]+", text) if p]
    lines, cur = [], ""
    for p in parts:
        while len(p) > maxc:  # 單一長句硬切
            if cur:
                lines.append(cur); cur = ""
            lines.append(p[:maxc]); p = p[maxc:]
        if cur and len(cur) + 1 + len(p) > maxc:
            lines.append(cur); cur = p
        else:
            cur = f"{cur} {p}".strip()
    if cur:
        lines.append(cur)
    return lines


def esc(t):
    return t.replace("\\", "＼").replace("{", "｛").replace("}", "｝")


def make_ass(script, shots, total, W, H, path):
    FONT = font_family()
    portrait = H > W
    fs = round((0.066 if portrait else 0.058) * min(W, H))
    maxc = max(8, int((W * 0.86) / fs))
    mv = round(H * (0.2 if portrait else 0.07))
    tfs = round(fs * 1.7)
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Sub,{FONT},{fs},&H00FFFFFF,&H00FFFFFF,&H00202020,&H80000000,1,0,0,0,100,100,1,0,1,{max(2, fs // 14)},{max(1, fs // 28)},2,40,40,{mv},1
Style: Speech,{FONT},{fs},&H0066E6FF,&H00FFFFFF,&H00202020,&H80000000,1,0,0,0,100,100,1,0,1,{max(2, fs // 14)},{max(1, fs // 28)},2,40,40,{mv},1
Style: Title,{FONT},{tfs},&H00FFFFFF,&H00FFFFFF,&H00303030,&H64000000,1,0,0,0,100,100,2,0,1,{max(3, tfs // 14)},{max(2, tfs // 20)},5,60,60,0,1
Style: Card,{FONT},{round(fs * 1.25)},&H00FFFFFF,&H00FFFFFF,&H00000000,&H96000000,1,0,0,0,100,100,1,0,3,{max(6, fs // 5)},0,8,60,60,{round(H * 0.1)},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    ev, srt = [], []

    def add(st, en, style, text, fx=""):
        # 先逐行跳脫再用 \N 接：舊寫法整串 esc() 會把換行碼 \N 變成「＼N」顯示出來（2026-11-15 Colab 實測）
        body = r"\N".join(esc(x) for x in text.split(r"\N"))
        ev.append(f"Dialogue: 0,{ass_time(st)},{ass_time(en)},{style},,0,0,0,,{fx}{body}")
        if style in ("Sub", "Speech"):
            srt.append((st, en, text.replace(r"\N", "\n")))

    if script.get("title"):
        tl = split_lines(script["title"], max(6, int(W * 0.84 / tfs)))
        # title_pos: "center"（預設，疊在畫面正中）| "top"（直式片放上方模糊區，開場畫面本身有字時用，例如布條）
        pos = rf"\an8\pos({W // 2},{round(H * 0.17)})" if script.get("title_pos") == "top" else ""
        add(0.15, min(2.8, total), "Title", r"\N".join(tl), r"{\fad(300,400)" + pos + "}")
    for sh in shots:
        if sh["voice"] is not None:
            lines = split_lines(sh["narration"], maxc)
            pairs = [lines[i:i + 2] for i in range(0, len(lines), 2)] if not portrait else [[l] for l in lines]
            vlen = len(sh["voice"]) / SR
            tot = sum(len("".join(p)) for p in pairs) or 1
            t0 = sh["start"] + LEAD
            for p in pairs:
                dt = vlen * len("".join(p)) / tot
                add(t0, t0 + dt, "Sub", r"\N".join(p))
                t0 += dt
        if sh["speech_caption"]:
            lines = split_lines(sh["speech_caption"], maxc)
            dt = sh["len"] / max(1, len(lines))
            for k, l in enumerate(lines):
                add(sh["start"] + k * dt, sh["start"] + (k + 1) * dt, "Speech", l)
        if sh["caption"]:
            add(sh["start"] + 0.1, sh["start"] + sh["len"] - 0.1, "Card", sh["caption"], r"{\fad(150,150)}")
    if script.get("outro"):
        add(max(0, total - 2.6), total - 0.1, "Title", script["outro"], r"{\fad(400,400)}")
    Path(path).write_text(head + "\n".join(ev) + "\n", encoding="utf-8")
    with open(Path(path).with_suffix(".srt"), "w", encoding="utf-8") as f:
        for k, (st, en, tx) in enumerate(srt, 1):
            f.write(f"{k}\n{srt_time(st)} --> {srt_time(en)}\n{tx}\n\n")
    return maxc


# ---------- 主程式 ----------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--draft", action="store_true")
    ap.add_argument("--name")
    a = ap.parse_args()
    d = project_dirs(a.project)
    script = read_json(d["script"] / "script.json")
    brief = read_json(d["script"] / "brief.json", {})
    index = read_json(d["media"] / "media_index.json")
    from write_script import validate
    errors, _ = validate(script, index, brief)
    if errors:
        raise SystemExit("[build] 腳本無效：" + "；".join(errors))
    cands = {c["id"]: c for c in index["candidates"]}
    work = d["media"] / "work"
    for sub in ("tts", "shots", "music"):
        (work / sub).mkdir(exist_ok=True)
    W, H = RATIOS[script.get("ratio", "9:16")]
    if a.draft:
        W, H = W // 2 // 2 * 2, H // 2 // 2 * 2
    # 微軟台灣男聲 YunJhe 會「試念成功、正式念失敗」時好時壞（2026-11-15 實測）：
    # 任何一句失敗就整片換下一個台灣聲音重排，保持全片同一個聲音。
    chain = [script["voice"]] + [v for v in ("zh-TW-HsiaoChenNeural", "zh-TW-YunJheNeural", "zh-TW-HsiaoYuNeural")
                                 if v != script["voice"]]
    requested = script["voice"]
    for v in chain:
        script["voice"] = v
        try:
            shots, total = plan(script, cands, work / "tts")
            break
        except TTSFail as e:
            print(f"[build] ⚠ {e}；改用下一個聲音", file=sys.stderr)
    else:
        sys.exit("Edge-TTS 全部台灣聲音都失敗（網路？微軟服務？）")
    if script["voice"] != requested:
        script["voice_requested"] = requested
    limit = min(MAX_SECONDS, brief.get("target_seconds", MAX_SECONDS) * 1.1)
    if total > limit + 0.5:
        sys.exit(f"[build] 成片 {total:.1f} 秒，超過上限 {limit:.0f} 秒 {total - limit:.1f} 秒：請刪鏡或縮短旁白")
    print(f"[build] {len(shots)} 鏡，總長 {total:.1f} 秒，{W}x{H}{'（草稿）' if a.draft else ''}")

    # 1) 逐鏡算圖
    crf, preset = (27, "veryfast") if a.draft else (20, "medium")
    tag = "d" if a.draft else "f"
    lst = []
    for sh in shots:
        out = work / "shots" / f"{tag}{sh['i']:02d}.mp4"
        render_shot(sh, W, H, script.get("fade", "none"), sh is shots[-1], out, crf, preset)
        lst.append(f"file '{out.name}'")
        print(f"[build]   鏡 {sh['i']:02d}/{len(shots)} {sh['cand']['id']} {sh['len']:.1f}s")
    (work / "shots" / f"{tag}_list.txt").write_text("\n".join(lst), encoding="utf-8")
    concat = work / f"{tag}_concat.mp4"
    run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", f"{tag}_list.txt", "-c", "copy",
         concat.resolve()], cwd=work / "shots")

    # 2) 旁白軌
    narr = np.zeros(int((total + 1) * SR), np.int32)
    for sh in shots:
        if sh["voice"] is not None:
            s0 = int((sh["start"] + LEAD) * SR)
            narr[s0:s0 + len(sh["voice"])] += sh["voice"]
    narr_wav = work / f"{tag}_narration.wav"
    write_wav(narr_wav, np.clip(narr[: int(total * SR)], -32768, 32767))
    has_voice = any(sh["voice"] is not None for sh in shots)

    # 3) 字幕
    ass = work / "subs.ass"
    make_ass(script, shots, total, W, H, ass)

    # 4) 混音＋燒字幕
    music = get_music(script, total, work / "music")
    name = safe_name(a.name or script.get("title", "成片"), 30)
    final = d["out"] / f"{name}_{'草稿' if a.draft else '定稿'}.mp4"
    # 混音與畫面分兩趟：同一個 filter_complex 同時燒字幕＋loudnorm＋無限循環音樂，在 ffmpeg 8.1 會死鎖（2026-11-15 實測）
    cmd = ["ffmpeg", "-v", "error", "-y", "-i", concat.resolve(), "-i", narr_wav.resolve()]
    voice_gain = 1.0
    fc = [f"[0:a]volume={0.55 if has_voice else 1.0}[orig]", f"[1:a]aresample={SR},aformat=channel_layouts=stereo,volume={voice_gain}[nar]"]
    mix_in = "[orig][nar]"
    n_in = 2
    if music:
        cmd += ["-stream_loop", "-1", "-t", f"{total + 1:.3f}", "-i", Path(music).resolve()]
        fc += [f"[nar]asplit[nar1][sc]",
               f"[2:a]aresample={SR},aformat=channel_layouts=stereo,atrim=duration={total:.3f},"
               f"loudnorm=I=-24:TP=-3:LRA=9,afade=in:d=1.5,afade=out:st={max(0, total - 2.5):.3f}:d=2.5[mus]",
               "[mus][sc]sidechaincompress=threshold=0.02:ratio=6:attack=30:release=500:makeup=1[duck]"]
        mix_in = "[orig][nar1][duck]"
        n_in = 3
    fc += [f"{mix_in}amix=inputs={n_in}:normalize=0:duration=first,loudnorm=I=-16:TP=-1.5:LRA=11[aout]"]
    sub_filter = "subtitles=subs.ass"
    font_path = find_font_path()
    if not font_path:
        raise SystemExit("[build] 缺少中文字型；請設定 PQC_FONT_FILE")
    font_dir = work / "fonts"
    font_dir.mkdir(exist_ok=True)
    shutil.copy2(font_path, font_dir / ("subtitle" + font_path.suffix))
    sub_filter += ":fontsdir=fonts"
    mix = work / f"{tag}_mix.wav"
    cmd += ["-filter_complex", ";".join(fc), "-map", "[aout]", "-t", f"{total:.3f}", "-ar", str(SR), mix.resolve()]
    run(cmd, cwd=work)
    run(["ffmpeg", "-v", "error", "-y", "-i", concat.resolve(), "-i", mix.resolve(), "-filter_complex",
         f"[0:v]{sub_filter}[vout]", "-map", "[vout]", "-map", "1:a", "-t", f"{total:.3f}",
         "-c:v", "libx264", "-preset", preset, "-crf", str(crf), "-pix_fmt", "yuv420p", "-r", str(FPS),
         "-c:a", "aac", "-b:a", "192k", "-ar", str(SR), "-movflags", "+faststart", final.resolve()], cwd=work)
    shutil.copy2(ass.with_suffix(".srt"), final.with_suffix(".srt"))
    timeline = [{"i": s["i"], "cand": s["cand"]["id"], "start": s["start"], "len": s["len"], "in": s["in"],
                 "freeze": s["freeze"], "narration": s["narration"], "keep_audio": s["keep_audio"]} for s in shots]
    write_json(d["out"] / "timeline.json", {"total": round(total, 2), "size": [W, H], "music": str(music) if music else None,
                                             "expect_audio": has_voice or bool(music) or any(s["keep_audio"] and s["cand"].get("has_audio") for s in shots),
                                             "voice": script["voice"], "voice_requested": script.get("voice_requested"),
                                             "final": str(final), "shots": timeline})
    print(f"[build] 完成：{final}（{duration(final):.1f} 秒）")
    print(f"FINAL={final}")


if __name__ == "__main__":
    main()
