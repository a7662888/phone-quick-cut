# 手機快剪（phone-quick-cut）

把手機照片與影片放進收件匣，附上一句文字或語音任務單，產生精華候選、台詞稿與分鏡預覽。使用者確認後，合成三分鐘內的影片、配音與字幕，再複製到成品資料夾。原始素材保留不動。

這是一個可供電腦端 Agent 讀取的技能，也是一組 Python 命令列工具。**任何能讀寫檔案、執行 Python 的 Agent 都可採手動協調模式；背景自動寫稿目前提供 Claude Code 與 Codex CLI 介面。** Agent 的技能自動發現、CLI 登入與模型額度須在各台電腦確認，不能由安裝檔案成功推論。

## 安裝

需要 Git、Python 3.10–3.13、FFmpeg／ffprobe，以及可顯示繁體中文的字型。先在自己的工作目錄下載：

```bash
git clone https://github.com/a7662888/phone-quick-cut.git
cd phone-quick-cut
python -X utf8 scripts/setup_env.py --install
```

安裝程式將 Python 套件放入 repo 的 `.venv`，不修改全域 Python。FFmpeg 與字型若缺少，依檢查結果安裝後再檢查。Windows 可安裝 Gyan.FFmpeg；macOS 可使用 Homebrew；Linux 可使用系統套件管理員。FFmpeg 需要 `libx264` 與字幕濾鏡。

接下來的 `python` 指已啟用的 repo 虛擬環境；也可直接使用：

| 系統 | Python 路徑 |
|---|---|
| Windows | `.venv\Scripts\python.exe` |
| macOS／Linux | `.venv/bin/python` |

```bash
python -X utf8 scripts/setup_env.py
python -X utf8 scripts/setup_env.py --agent codex
```

第一個命令檢查必要依賴；第二個額外檢查指定 CLI。檢查失敗會以非零退出碼結束。檢查不會提交影片、呼叫付費模型或建立排程。

若要讓 Agent 自動發現技能，把 repo 放在該產品目前支援的技能目錄下，或由產品提供的技能安裝功能加入。也可直接請 Agent 讀取這個 repo 的 `SKILL.md`；這不依賴特定技能目錄規則。

## 路徑設定

預設尋找目前使用者的 OneDrive，收件匣與成品位於 `手機快剪/收件匣`、`手機快剪/成品`。沒有偵測到 OneDrive 時使用本機 Videos，**本機備援目錄本身沒有手機同步能力**。專案預設存放在使用者的 Videos/PhoneQuickCut。

| 環境變數 | 用途 |
|---|---|
| `PQC_INBOX` | 收件匣根目錄 |
| `PQC_OUTBOX` | 成品根目錄 |
| `PQC_VIDEO` | 剪輯專案母目錄 |
| `PQC_FONT_FILE` | 中文字型檔絕對路徑 |
| `PQC_FONT_FAMILY` | 該字型的家族名稱，供字幕使用 |
| `PQC_PRONUNCIATION` | 自訂讀音表 JSON；預設使用 repo 內 `assets/pronunciation_zh.json` |

先設定變數，再執行安裝檢查與排程產生器。OneDrive 素材應設為保留在本機，並等候同步完成。

## 由目前的 Agent 協調剪片

這個方式適用 Codex、Claude Code、Antigravity、OpenCode，或其他具備本機檔案與終端機能力的 Agent：

```bash
python -X utf8 scripts/run_job.py --src "<收件匣子夾>" --mode manual
```

程式接件與分析後停在「待寫稿」。Agent 讀取專案的 `brief.json`、`media_index.json` 與接觸表，依 [腳本格式](references/script-format.md) 和 [風格參考](references/styles.md) 寫入 `01_查核與腳本/script.json`，再送審：

```bash
python -X utf8 scripts/run_job.py --project "<專案夾>" --submit-script
```

使用者看過 `_台詞稿.txt`、`_分鏡預覽.jpg` 並確認後，才執行：

```bash
python -X utf8 scripts/run_job.py --project "<專案夾>" --approve
```

修改台詞時先更新腳本再 `--submit-script`，重新取得確認；不要沿用舊稿的確認。合成後還會執行 QA，失敗不會交付為完成。

## 自動寫稿與背景掃描

```bash
python -X utf8 scripts/run_job.py --src "<收件匣子夾>" --mode agent --agent codex
python -X utf8 scripts/run_job.py --src "<收件匣子夾>" --mode template
```

| 模式 | 寫稿來源 | 需求與限制 |
|---|---|---|
| `manual` | 目前的主 Agent | 停在待寫稿，由 Agent 看圖並寫檔 |
| `agent` | Claude／Codex CLI | CLI 可執行、已登入且有可用額度；可能將畫面與文字送到其服務 |
| `llm` | 文字 LLM | 只有文字，不能看畫面；本機 OpenRouter 需金鑰及 `PQC_ALLOW_CLOUD=1` |
| `template` | 本機固定模板 | 不呼叫寫稿模型；能力較有限，審稿時會標示來源 |
| `auto` | 可用模式逐級備援 | 依執行環境選擇；不會因存在金鑰就自動開啟 OpenRouter 文字外送 |

文字 LLM 的 `OPENROUTER_API_KEY`、允許外送設定，以及 CLI 認證都是使用者自己的；repo 不附憑證。無論寫稿來源為何，預設仍先送台詞稿供人確認。

設定背景掃描前，可先手動掃描一次：

```bash
python -X utf8 scripts/watch_inbox.py --once --agent codex
python -X utf8 scripts/install_schedule.py
```

排程產生器使用目前 Python 的絕對路徑，並保存當次資料目錄設定。先檢查產出的啟動器與命令；Windows 只有加上 `--install` 才建立排程。macOS／Linux 請依產生器提供的排程指引設定。它不會因讀取本文件而修改排程。

## 手機端操作

1. 在收件匣建立子資料夾，放照片／影片，以及 `任務.txt` 或語音備忘。例如：「主題是陽明山，溫馨風格，一分鐘，直式，女聲」。可加「不要音樂」「不要旁白」「保留原音」。
2. 電腦產生 `_台詞稿.txt` 與 `_分鏡預覽.jpg` 後先審閱。使用背景掃描時，放入 `確認.txt`／`OK.txt` 表示確認；放入 `修改1.txt` 或修改語音表示重寫。
3. 完成時在成品夾取得 MP4 與 SRT；失敗時看 `_狀態.txt`。處理時間依硬體、素材、模型與網路而定。

## 配音、配樂與資料外送

- 配音使用 Edge-TTS 台灣語音，會將旁白文字傳送至微軟服務；無網路時請選不要旁白。
- 讀音表包含 repo 內的替換規則，只影響送入 TTS 的文字，不改字幕。
- 預設可使用本機合成和弦。Lyria 工具已隨 repo 提供；只有設定自己的 `OPENROUTER_API_KEY` 並明確開啟 `PQC_ALLOW_PAID_MUSIC=1` 才使用，可能產生費用。
- MusicGen 是選配：在虛擬環境安裝 `requirements-musicgen.txt`，再於腳本明確指定 `music.provider: "musicgen"`；第一次會下載模型，CPU 可能較慢。
- 雲端 LLM、Agent CLI、TTS 與 Colab 都有各自資料流。含可辨識人物的素材，先確認使用者允許相應外送；病人、病歷與研究受試者資料不應投入這個生活影片雲端流程。

## Colab 與驗證

電腦關機時可把 `colab/phone_quick_cut.ipynb` 複製到自己的 Google 雲端硬碟，用 Colab 開啟；操作見 [Colab 備援](references/colab-fallback.md)。Colab 使用文字／模板寫稿，不能取代能看畫面的 Agent 審稿。

```bash
python -m unittest discover -s tests -v
python -X utf8 scripts/make_colab_nb.py --check
python -X utf8 scripts/smoke_test.py
```

測試使用人工素材，離線驗證核心流程；不代表各產品的自動技能發現、付費模型、手機同步或 Colab 服務已經實機驗收。CI 在 Windows、macOS、Linux 執行核心測試；實際支援狀態以成功的工作流程結果為準。

原始碼採 [MIT License](LICENSE)。依賴套件、模型、字型與音樂服務各有自己的授權及使用條款。
