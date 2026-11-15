---
name: phone-quick-cut
description: 手機拍的日常照片影片丟進 OneDrive「手機快剪」收件匣，自動剪成 3 分鐘內有主題的短片：精華挑選、五種風格（創意／溫馨／幽默／知識／藝術）、中文配音、字幕、AI 配樂，可選 9:16／16:9／1:1／4:5，成片回傳 OneDrive；電腦關機時改用 Colab notebook 從手機跑。醫學或衛教插圖短片→illustrated-short-video；要逐字精修的口播剪輯→chatgpt-short-video-editor。觸發：手機快剪、日常影片剪輯、旅遊短片、生活 vlog、出遊影片、照片影片做成短片、戶外快速剪片。
---

# 手機快剪（phone-quick-cut）

業主在戶外用手機拍照錄影，丟進 OneDrive，電腦自動剪成短片再放回 OneDrive。**手機端只做三件事：拍、丟、講一句任務單。**

## 業主操作（手機）

1. OneDrive 開 `手機快剪/收件匣/`，新增一個子夾（名稱隨意，如「陽明山」），放 5–30 個照片影片。
2. 同一夾放一段語音備忘（任意檔名的 m4a／mp3），講一句任務單，例如：
   「主題是陽明山芒草，溫馨風格，兩分鐘，直式，女聲」。沒講到的用預設：溫馨、90 秒、9:16、男聲、有配樂。
   也可改放 `任務.txt`。其他關鍵字：「不要音樂」「保留原音」「不要旁白」。
3. **審台詞（2026-11-15 業主定案：成片前一律先審）**：約 3–5 分鐘後同一夾出現 `_狀態.txt：待審閱`、`_台詞稿.txt`、`_分鏡預覽.jpg`。
   - 同意 → 放一個「確認」開頭的檔（錄音存成「確認」最快；`OK`、`同意` 開頭也算）。
   - 要改 → 放「修改」開頭的語音或文字（「第3句改成…」「刪掉第5鏡」），改好會再送一次台詞稿。
4. 確認後約 3–10 分鐘，`_狀態.txt` 變「完成」，成片在 `手機快剪/成品/`。成片後再放「修改」檔，同樣先改台詞再送審。

## 自動流程（電腦開機時）

Windows 工作排程器每 5 分鐘跑 `watch_inbox.py --once`，發現「有素材＋有任務單＋兩分鐘沒變動」的子夾就跑 `run_job.py`：

| 步驟 | 腳本 | 產出 | 要點 |
|---|---|---|---|
| 1 接件 | `intake.py` | `Video\<日期>_手機快剪_<主題>\`、`brief.json` | 素材**複製**不搬移；語音任務單用 faster-whisper large-v3-turbo 轉文字再關鍵字解析 |
| 2 精華 | `analyze.py` | `media_index.json`、`04_QA\素材接觸表_N.jpg` | 影片每秒評分（清晰 50%、曝光 30%、晃動 20%），每支挑 1–4 段；有人講話的段落對齊整句 |
| 3 腳本 | `write_script.py` | `script.json` | 無頭 agent 看接觸表寫腳本；格式見 [script-format.md](references/script-format.md)，風格見 [styles.md](references/styles.md) |
| 3.5 審閱 | `review.py` | `_台詞稿.txt`、`_分鏡預覽.jpg`、狀態「待審閱」 | **預設停在這裡**等業主「確認」檔；`--no-review` 或 `PQC_REVIEW=0` 才跳過。互動對話中由 agent 執行時，也要先把台詞稿貼給業主看 |
| 4 合成 | `build.py` | `03_成片\<片名>_定稿.mp4`＋`.srt` | Edge-TTS 逐鏡配音、照片 Ken Burns、比例不合用模糊背景、音樂說話時自動壓低、-16 LUFS、燒字幕 |
| 5 QA | `qa.py` | `04_QA\qa.json`、`成片接觸表.jpg` | 長度 ≤ 180 秒、響度、真峰值、黑畫面、旁白聽寫比對 |
| 6 交付 | `deliver.py` | OneDrive `成品\`、`_狀態.txt`、`HANDOFF.md` | 失敗也會寫 `_狀態.txt` 說明原因 |

手動執行（任何 agent）：

```bash
py -3 -X utf8 D:/secondbrain/Skills/phone-quick-cut/scripts/run_job.py --src "E:/OneDrive/手機快剪/收件匣/<子夾>" --agent codex   # 到送審為止
py -3 -X utf8 D:/secondbrain/Skills/phone-quick-cut/scripts/run_job.py --project "<專案夾>" --revise "<修改要求>"            # 改台詞再送審
py -3 -X utf8 D:/secondbrain/Skills/phone-quick-cut/scripts/run_job.py --project "<專案夾>" --approve                        # 業主確認後合成交付
```

## 寫腳本的三種模式（`--mode auto` 依序退）

1. **agent**：`--agent claude|codex`，失敗自動換另一個。Codex 用 `codex exec -i <接觸表>`（2026-11-15 實測可用）。Claude 桌面版附帶的 `claude.exe` **沒登入 CLI**，要在終端機跑一次 `claude` 登入後才能無頭執行，所以排程預設用 Codex（`PQC_AGENT=codex`）。
2. **llm**：只送文字（任務單、拍攝時間、現場講話逐字稿），不送畫面，走 OpenRouter `google/gemini-2.5-flash`；Colab 上用內建 Colab AI。
3. **template**：不用 AI，依分數與時間排片，只有開頭結尾旁白（保底）。

**你被呼叫來寫腳本時**：讀 `brief.json`、`media_index.json`、看接觸表，依 styles.md 寫 `script.json`，只寫這個檔。旁白只描述看得到或任務單說過的事；`guessed` 列出的欄位（業主沒講、用預設的）照預設即可。

## 配音與配樂

- 配音：Edge-TTS 台灣語音（男 `zh-TW-YunJheNeural`、女 `zh-TW-HsiaoChenNeural`），套共用讀音表 `_shared/tts_pronunciation_zh.json`。微軟端偶發 `NoAudioReceived`，程式會重試 3 次。
- 定稿想用業主聲紋（大豪）：先出 Edge 版，再依 CLAUDE.md 聲紋規則改用 VoxCPM2 重配（不在本技能自動流程內，因為太慢）。
- 配樂 `provider: auto`：本機用 Lyria（`slide-video-workflow/scripts/lyria_bgm.py`，pro 版每首約 US$0.08，OpenRouter 計費）；Colab 用 MusicGen-small；都失敗用內建合成和弦（保底，品質普通）。一律純音樂、可商用性以各服務條款為準，上傳社群前業主自行確認。

## 電腦關機時：Colab 備援

`colab/phone_quick_cut.ipynb`（由 `scripts/make_colab_nb.py --copy-to-gdrive` 產生並複製到 `G:\我的雲端硬碟\Colab\`，**改任何腳本後要重跑**）。

- **手機實測教訓（2026-11-15）**：手機瀏覽器切 App 就斷線（`await connected: disconnected`），逐格執行與 `files.upload`／`files.download` 必卡。所以 notebook 只有**一個儲存格**：按一次 ▶ 雲端跑到底；素材從 Google 雲端硬碟資料夾讀、結果寫回同夾；`try/finally` 保證 `runtime.unassign()` 關機。
- 審閱：表單「階段」先「出台詞稿」→ 看 `_台詞稿.txt` → 改「台詞已確認，合成」再按一次。
- 預設 CPU 執行階段（不需 GPU）。Colab 寫腳本只送文字、看不到畫面，品質低於電腦版。
- 2026-11-15 實測成功（約 4 分鐘、自動關機確認）；**授權按「允許」前螢幕不能暗**，否則卡在 `drive.mount`。實測細節見 colab-fallback.md。
- 細節與限制見 [colab-fallback.md](references/colab-fallback.md)。

## 安裝與排程（一次性，業主同意後才做）

```powershell
# 每 5 分鐘掃收件匣（隱藏視窗、用 Codex 寫腳本）；2026-11-15 已註冊
schtasks /Create /TN "PhoneQuickCut" /SC MINUTE /MO 5 /F /TR "wscript.exe \"D:\secondbrain\Skills\phone-quick-cut\scripts\run_watch.vbs\""
```

- `run_watch.vbs` 必須**純 ASCII**：wscript 用 ANSI 讀檔，中文註解會吃掉下一行（實測錯誤「此處需要物件 'sh'」）。

- OneDrive 的 `手機快剪` 資料夾要設「一律保留在此裝置上」，否則檔案是雲端預留位置，讀取會慢。
- iPhone HEIC 照片需 `py -3 -m pip install pillow-heif`，或把相機格式改「最相容」。
- 偵測剪接點需 `py -3 -m pip install scenedetect`（用現有 OpenCV；2026-11-15 已裝 0.7.3）。

## 已知限制與踩坑

| 問題 | 做法 |
|---|---|
| Whisper small 把「週末」聽成「周目」 | 任務單改用 large-v3-turbo（短音檔，CPU 約 20 秒） |
| `edge-tts.exe` 被應用程式控制原則封鎖 | 一律 `python -m edge_tts` |
| 旁白比鏡頭長 | `build.py` 自動拉長鏡頭；影片素材不夠就往前借，再不夠停格 |
| 超過 180 秒 | `build.py` 中止並報超多少秒，請刪鏡或縮短旁白 |
| 素材全是同一支長影片 | `analyze.py` 每 20 秒多挑一段，上限 4 段；腳本可用 `in` 自選起點 |
| 測試素材是色塊時 agent 會標「示意畫面」 | 正常行為：不編造畫面沒有的內容 |
| 挑段跨過影片內的剪接點（2026-11-15 實例：第 1 鏡 6 秒內換三個畫面，紅布條只閃 1.9 秒） | 2026-11-15 已修：`analyze.py` 用 PySceneDetect 偵測剪接點，每個 ≥ 1.5 秒的鏡頭各自挑段，短鏡頭整段當候選；`build.py` 拉長時先在同鏡頭內借素材或停格（≤ 2 秒）。沒裝 `scenedetect` 會印警告並退回舊行為。auto-editor 對聚餐錄影無效。紀錄見 `_shared/VIDEO_TOOL_CANDIDATES.md` |

## 鐵律

- 收件匣原檔不改、不搬、不刪；專案一律放 `D:\secondbrain\Video\<日期>_手機快剪_<主題>\`。
- 拍攝內容由業主自行把關；家人影像不送公開服務以外的地方，Colab 執行完一律關機。
- 交付前看 `成片接觸表.jpg`；配樂與旁白聲音要請業主親耳確認（agent 聽不到）。
- 個人生活影片不登錄 Obsidian 成品總覽（含家人肖像）；業主要求才登錄。
