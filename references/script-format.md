# script.json 格式

寫在專案的 `01_查核與腳本/script.json`，UTF-8：

```json
{
  "title": "陽明山的芒草季",
  "style": "溫馨",
  "ratio": "9:16",
  "voice": "zh-TW-YunJheNeural",
  "rate": "+0%",
  "fade": "soft",
  "title_pos": "top",
  "music": {
    "enabled": true,
    "prompt": "warm acoustic guitar and soft piano, gentle, 80 bpm",
    "provider": "auto"
  },
  "shots": [
    {"cand": "c03", "dur": 4.0, "narration": "風一吹，山坡的芒草跟著搖。"},
    {"cand": "c05", "keep_audio": true, "speech_caption": "哇，你看那邊！"},
    {"cand": "c07", "dur": 1.9, "narration": "", "caption": "這一刻"}
  ],
  "outro": "秋日記憶"
}
```

範例 id 僅示意；實際只能引用當次 `media_index.json` 的候選，不能照抄不存在的 id。

| 欄位 | 必填 | 說明 |
|---|---|---|
| `title` | 是 | 片名，疊在開場 |
| `style`、`ratio`、`voice` | 是 | 原則上從 brief 帶入；比例為 9:16、16:9、1:1、4:5 |
| `rate` | 否 | Edge-TTS 語速，例如 +0%、+10%、-5% |
| `fade` | 否 | soft 或 none |
| `title_pos` | 否 | center（預設）或 top；開場畫面有布條／招牌時可移上方 |
| `music.enabled` | 否 | false 不配樂 |
| `music.provider` | 否 | auto、lyria、musicgen、synth；見下方 |
| `shots` | 是 | 非空鏡頭陣列 |
| `shots[].cand` | 是 | 當次候選 id |
| `shots[].in` | 否 | 覆蓋起點（秒），必須仍在候選的 scene 內 |
| `shots[].dur` | 否 | 正數秒數；實際長度會包含旁白需要的時間 |
| `shots[].narration` | 否 | 該鏡旁白，空字串表示不唸 |
| `shots[].keep_audio` | 否 | 保留現場聲音；有旁白時壓低現場聲 |
| `shots[].speech_caption` | 否 | 核對過的現場講話字幕 |
| `shots[].caption` | 否 | 畫面字卡 |
| `outro` | 否 | 片尾字卡，可空 |

## 鏡頭與旁白長度

影片候選的 `scene` 是所在鏡頭的起迄秒數。程式會在同一鏡頭內借素材，必要時停格最多兩秒；仍不足時中止並要求縮短旁白、換候選或分鏡。不能把 `in` 改到其他鏡頭來繞過限制。短鏡頭（例如不到兩秒的布條）適合只放字卡。

估計旁白時用每秒約四字並留呼吸空間，合成後以實際 TTS 長度為準。總長（含旁白撐長與停格）須同時不超過 `brief.target_seconds` 的 110% 與 180 秒。

## 配樂選擇

- `auto`：使用可用且已明確允許的 provider；沒有付費服務授權時以本機合成和弦備援。
- `lyria`：需 `OPENROUTER_API_KEY` 與 `PQC_ALLOW_PAID_MUSIC=1`；工具已隨 repo 提供。
- `musicgen`：明確選用後才載入；需先在虛擬環境安裝 `requirements-musicgen.txt`，首次下載模型。
- `synth`：本機 numpy 合成和弦，不呼叫外部音樂服務。

降級結果會寫入 QA 警告；不要把合成和弦稱為成功生成的 Lyria 音樂。
