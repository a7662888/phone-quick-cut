"""Optional OpenRouter Lyria music; never searches outside this repository for keys.

Requires OPENROUTER_API_KEY and PQC_ALLOW_PAID_MUSIC=1. No API call is made by doctor/tests.
Protocol: https://openrouter.ai/docs/guides/overview/multimodal/audio (2026-11-16).
"""
import argparse
import base64
import json
import os
from pathlib import Path

from pqc_common import api_key, env_enabled


def decode_audio(chunks):
    # Some providers send separately padded blocks; others split one base64 string.
    if any("=" in chunk for chunk in chunks[:-1]):
        return b"".join(base64.b64decode(chunk, validate=True) for chunk in chunks)
    return base64.b64decode("".join(chunks), validate=True)


def generate(prompt, out, model, seed=None):
    if not env_enabled("PQC_ALLOW_PAID_MUSIC"):
        raise RuntimeError("Lyria 是付費選配；須先設定 PQC_ALLOW_PAID_MUSIC=1")
    key = api_key()
    if not key:
        raise RuntimeError("Lyria 需要 OPENROUTER_API_KEY")
    import requests
    body = {"model": model, "modalities": ["text", "audio"], "stream": True,
            "messages": [{"role": "user", "content": prompt + " Instrumental only, no vocals, no lyrics."}]}
    if seed is not None:
        body["seed"] = seed
    with requests.post("https://openrouter.ai/api/v1/chat/completions", timeout=(30, 300), stream=True,
                       headers={"Authorization": f"Bearer {key}"}, json=body) as response:
        if response.status_code != 200:
            raise RuntimeError(f"Lyria HTTP {response.status_code}；請確認模型可用性、帳號額度與金鑰")
        chunks = []
        for line in response.iter_lines(decode_unicode=True):
            if isinstance(line, bytes):
                line = line.decode("utf-8")
            if not line or not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if payload == "[DONE]":
                break
            event = json.loads(payload)
            if event.get("error"):
                raise RuntimeError("Lyria 串流回報錯誤；未產生配樂")
            for choice in event.get("choices", []):
                audio = (choice.get("delta") or {}).get("audio") or {}
                if audio.get("data"):
                    chunks.append(audio["data"])
        if not chunks:
            raise RuntimeError("Lyria 沒有回傳音訊；未產生配樂")
        data = decode_audio(chunks)
        if not data:
            raise RuntimeError("Lyria 回傳空音訊")
        out = Path(out)
        out.parent.mkdir(parents=True, exist_ok=True)
        temp = out.with_suffix(out.suffix + ".part")
        temp.write_bytes(data)
        temp.replace(out)
        return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompt", required=True)
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--model", default=os.environ.get("PQC_MUSIC_MODEL", "google/lyria-3-pro-preview"))
    ap.add_argument("--seed", type=int)
    a = ap.parse_args()
    try:
        path = generate(a.prompt, a.out, a.model, a.seed)
    except Exception as e:
        raise SystemExit(f"[lyria] {e}")
    print(f"[lyria] 已產生 {path}")


if __name__ == "__main__":
    main()
