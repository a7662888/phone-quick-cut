---
name: phone-quick-cut
description: 將手機照片與影片整理成短片，產出台詞與分鏡供人確認後合成配音字幕。適用手機快剪、生活 vlog、旅遊與活動短片。
---

# 手機快剪

把收件匣素材複製至獨立專案，分析精華候選，先審台詞與分鏡，再合成不超過三分鐘的 MP4／SRT。命令均從本技能根目錄執行；使用 repo `.venv` 的 Python。安裝與環境設定見 [README](README.md)，開工先跑 `python -X utf8 scripts/setup_env.py`。

## 先選執行方式

- **目前主 Agent 協調**：任何能讀圖、讀寫檔案、執行 Python 的 Agent 可使用 `manual`。這是跨 Agent 的共同介面。
- **背景自動寫稿**：`agent` 模式目前僅提供已登入的 Claude／Codex CLI；先跑 `setup_env.py --agent claude` 或 `--agent codex`。
- **文字／模板備援**：`llm` 無法看圖；本機 OpenRouter 需 `OPENROUTER_API_KEY` 與 `PQC_ALLOW_CLOUD=1`。本機 `template` 不呼叫寫稿模型，成稿須標明來源。不要把成功退回模板說成 AI 已看過畫面。

## 主 Agent 工作流程

```bash
python -X utf8 scripts/run_job.py --src "<收件匣子夾>" --mode manual
```

停在「待寫稿」後：

1. 讀專案 `01_查核與腳本/brief.json`、`02_素材/media_index.json`，看其中列出的所有接觸表。
2. 依 [腳本格式](references/script-format.md) 與 [五種風格](references/styles.md) 寫 `01_查核與腳本/script.json`。只描述素材可見或使用者明確提供的事，不推測人名、地點或事件。
3. 執行下列命令驗證並產生審稿檔，把台詞與分鏡交給使用者確認：

```bash
python -X utf8 scripts/run_job.py --project "<專案夾>" --submit-script
```

4. 使用者確認**目前版本**後才合成交付：

```bash
python -X utf8 scripts/run_job.py --project "<專案夾>" --approve
```

修改稿先再次送審。腳本來源、缺省任務欄位、配樂降級及 QA 警告都應在審稿或交付時說明。程式退出失敗時查看專案 `04_QA` 與收件匣 `_狀態.txt`，修正後再執行，不宣稱已完成。

## 自動流程

```bash
python -X utf8 scripts/run_job.py --src "<收件匣子夾>" --mode agent --agent codex
python -X utf8 scripts/run_job.py --src "<收件匣子夾>" --mode template
python -X utf8 scripts/watch_inbox.py --once --agent codex
```

預設停在「待審閱」。背景掃描只在發現確認檔後合成；有修改檔時先改稿重新送審。排程由 `scripts/install_schedule.py` 產生，檢查後才明確安裝；不要直接套用其他電腦的排程路徑。

## 剪輯與交付條件

- 原始素材只複製，不改、不搬、不刪。資料落點由 `PQC_INBOX`／`PQC_OUTBOX`／`PQC_VIDEO` 決定。
- 影片候選帶 `scene`。拉長時只在同鏡頭內借素材或停格最多兩秒；仍不足就縮短台詞、換候選或分鏡，不能跨剪接點補足。
- 開場畫面已有文字時可用 `title_pos: "top"`。分鏡預覽只核對選片與台詞；標題遮擋須在確認台詞後，看合成草稿或成片確認。
- 總長不得超過任務目標的 110% 或 180 秒。素材不足時可短於目標，須告知。
- QA FAIL 不交付為完成；PASS 仍要查看成片接觸表，並請使用者試聽。旁白、字型、現場音與配樂降級不得靜默略過。

## 配音、配樂與外送

Edge-TTS 會傳送旁白文字。讀音表隨 repo 提供，`PQC_PRONUNCIATION` 可覆蓋。Lyria 使用隨 repo 的工具，需金鑰與 `PQC_ALLOW_PAID_MUSIC=1`；沒有明確開啟時用本機配樂。MusicGen 需選配依賴與明確指定 provider。

Agent CLI 可能傳送接觸表及任務內容；文字 LLM 只傳文字但仍屬外送。確認使用者同意相應服務，病人、病歷與研究受試者資料不走這套生活影片雲端流程。

## Colab 與維護

電腦關機備援讀 [Colab 操作](references/colab-fallback.md)。修改程式、腳本格式、讀音資產或需求檔後，重新產生 notebook 並跑 `scripts/make_colab_nb.py --check`；不要把桌面版通過推論為雲端已驗證。
