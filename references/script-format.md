# script.json 格式（寫在 `01_查核與腳本\script.json`）

```json
{
  "title": "陽明山的芒草季",
  "style": "溫馨",
  "ratio": "9:16",
  "voice": "zh-TW-YunJheNeural",
  "rate": "+0%",
  "fade": "soft",
  "music": {"enabled": true, "prompt": "warm acoustic guitar and soft piano, gentle, 80 bpm", "provider": "auto"},
  "shots": [
    {"cand": "c03", "dur": 4.0, "narration": "十一月的陽明山，風一吹，整片山坡都在發光。"},
    {"cand": "c05", "keep_audio": true, "speech_caption": "哇，你看那邊！"},
    {"cand": "c07", "in": 12.5, "dur": 3.0, "narration": "", "caption": "第一站：擎天崗"}
  ],
  "outro": "2026 秋・陽明山"
}
```

| 欄位 | 必填 | 說明 |
|---|---|---|
| `title` | ✓ | 片名，疊在第一鏡上 2.5 秒 |
| `style` `ratio` `voice` | ✓ | 從 `brief.json` 帶入；比例可為 `9:16` `16:9` `1:1` `4:5`；聲音 `zh-TW-YunJheNeural`（男）、`zh-TW-HsiaoChenNeural`（女） |
| `rate` | | 語速，`+0%`、`+10%`、`-5%` |
| `fade` | | `soft`（每鏡 0.25 秒淡入淡出）或 `none`（硬切） |
| `music.enabled` | | `false` 就不配樂 |
| `music.provider` | | `auto`（本機有 OpenRouter 金鑰→Lyria；Colab→MusicGen；都沒有→內建合成）、`lyria`、`musicgen`、`synth` |
| `title_pos` | | 片頭標題位置：`center`（預設）或 `top`（直式片放上方模糊區；開場畫面本身有字，例如紅布條、招牌時用，免得疊字） |
| `shots[].cand` | ✓ | 只能填 `media_index.json` 裡的候選 id |
| `shots[].in` `dur` | | 覆蓋候選的起點與長度（秒）；旁白比鏡頭長時，程式會自動拉長該鏡 |
| `shots[].narration` | | 該鏡開始時唸的旁白；空字串＝不唸 |
| `shots[].keep_audio` | | 保留現場聲音（有旁白時會自動壓低現場聲） |
| `shots[].speech_caption` | | 現場講話的字幕（已修正為繁中） |
| `shots[].caption` | | 畫面上方的大字卡（重點標題、吐槽） |
| `outro` | | 片尾字卡文字，疊在最後一鏡最後 2.5 秒 |

**長度規則**：所有鏡頭加總（含旁白撐長的部分）必須 ≤ `brief.target_seconds` 的 110%，且絕對 ≤ 180 秒。`build.py` 超過時會中止並告訴你超多少秒，請刪鏡或縮短旁白後重跑。

**影片候選不跨剪接點**：影片候選帶 `scene`（所在鏡頭的起迄秒數）。旁白比鏡頭長時，程式先在同一鏡頭內借素材，不夠就停格（最多 2 秒），超過才跨到別的畫面。所以短鏡頭（例如 1.9 秒的紅布條）旁白要短，或不配旁白、只放字卡。
