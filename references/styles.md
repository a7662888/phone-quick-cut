# 五種風格模板

寫 `script.json` 時依 `brief.style` 套用。旁白字數以「每秒約 4 字」估：目標 90 秒約 250–320 字，180 秒上限約 550 字（要留呼吸，不要塞滿）。

| 風格 | 鏡頭節奏 | 每鏡長度 | 旁白 | 轉場 `fade` | 音樂提示詞（給 Lyria／MusicGen） |
|---|---|---|---|---|---|
| 創意 | 快切、出人意料的排序（倒敘、先結果後原因） | 1.5–3 秒 | 俏皮、有一個反轉或設問；每句 ≤ 15 字 | `none` | upbeat quirky indie pop, plucky synths, claps, 110 bpm |
| 溫馨 | 依時間順序、長鏡頭、人臉與手部特寫優先 | 3–6 秒 | 第一人稱、像寫給家人的信；具體細節（天氣、味道、一句話） | `soft` | warm acoustic guitar and soft piano, gentle, heartfelt, 80 bpm |
| 幽默 | 快慢對比：鋪陳慢、笑點快；可定格吐槽 | 1–4 秒 | 自嘲、旁白吐槽畫面；可用 `caption` 放大字卡吐槽 | `none` | playful comedic pizzicato, light percussion, bouncy, 120 bpm |
| 知識 | 分段：開場提問 → 2–4 個重點 → 一句收尾 | 3–5 秒 | 清楚、一段一重點；每個重點用 `caption` 下標題 | `none` | light corporate ambient, soft marimba and pads, curious, 95 bpm |
| 藝術 | 留白、慢、空景與光影優先 | 4–7 秒 | 極少旁白（全片 ≤ 6 句）、短句、詩意；可完全不配音 | `soft` | ambient cinematic, slow evolving pads, felt piano, minimal, 60 bpm |

## 共通寫法

- **開場三秒抓人**：第一鏡選最好看的畫面，`title` 會疊在第一鏡上，旁白第一句就點題。
- **結尾留一個餘韻**：最後一鏡放慢、收在一句話或一個畫面；`outro` 是片尾字卡（可空）。
- **現場聲音**：候選片段有 `speech_text`（有人講話）而且內容有趣時，設 `keep_audio: true`、該鏡不放旁白，`speech_caption` 填修正過的繁中字幕（Whisper 可能聽錯或出簡體，要改）。
- **不編造**：旁白只描述畫面看得到或任務單明確說過的事；不要從模糊畫面、檔名或時間自行推測人名、地點或事件。
- **繁體中文、台灣用語**；數字用阿拉伯數字寫在字幕上沒關係，配音會照念。
- 避開 `weak: true` 的候選（模糊、過暗、劇烈晃動），除非那是唯一的關鍵畫面。
- 風格建議的鏡頭長度必須服從候選的 `scene` 邊界。短鏡頭可只放字卡；旁白太長時先縮短句子或換候選，不靠跨鏡頭延長。
