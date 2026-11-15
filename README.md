# 手機快剪（phone-quick-cut）

手機拍完照片與影片丟進 OneDrive「手機快剪/收件匣」，講一句語音任務單，電腦自動挑選精華、避開原本剪接點、生成台詞稿與分鏡預覽讓你審閱；確認後自動配音、配樂、燒錄字幕並輸出高畫質短片到「成品」資料夾。

---

## 🤖 給你的 AI Agent 看（一鍵自動安裝與啟用）

如果你是剛被使用者呼叫的電腦端 AI Agent（Claude Code / Codex / Antigravity / OpenCode），且**這台電腦可能尚未安裝任何必要軟體**，請依以下步驟完成安裝與設定：

1. **將本技能安裝到 Agent 技能目錄**（擇一或依目前使用的 Agent 放置）：
   - Antigravity：`~/.gemini/antigravity/skills/phone-quick-cut`（或全域 `~/.gemini/config/skills/phone-quick-cut`）
   - Claude Code：`~/.claude/skills/phone-quick-cut`
   - Codex：`~/.codex/skills/phone-quick-cut`
   ```bash
   git clone https://github.com/a7662888/phone-quick-cut.git
   ```
2. **檢查並補齊必要系統軟體（假設電腦尚未安裝）**：
   - **Python 3.10+**：執行 `python --version` 或 `py -3 --version` 確認；若無，請先安裝 Python 3.10+。
   - **FFmpeg + ffprobe（必備）**：
     - Windows：`winget install -e --id Gyan.FFmpeg`（安裝後需重開終端機或重載 PATH）
     - macOS：`brew install ffmpeg`
     - Ubuntu/Debian：`sudo apt-get update && sudo apt-get install -y ffmpeg`
3. **執行自動環境檢查與相依套件安裝**：
   ```bash
   python -X utf8 scripts/setup_env.py --install
   ```
   此腳本會自動安裝 `requirements.txt` 中的所有套件（`edge-tts`、`faster-whisper`、`scenedetect[opencv]`、`opencv-python`、`pillow`、`pillow-heif`、`numpy`、`requests`），並建立預設的 `手機快剪/收件匣`、`手機快剪/成品` 與專案目錄。
4. **確認路徑設定（選用環境變數）**：
   預設會自動偵測使用者的 `OneDrive/手機快剪/`（找不到 OneDrive 時改用 `~/Videos/手機快剪/`）。若要自訂位置，設定環境變數：
   - `PQC_INBOX`：收件匣資料夾路徑
   - `PQC_OUTBOX`：成品資料夾路徑
   - `PQC_VIDEO`：剪輯專案暫存與輸出母夾
5. **（選用）設定背景自動掃描**：
   - Windows 可用工作排程器每 5 分鐘執行 `scripts/watch_inbox.py --once`（詳見 [SKILL.md](SKILL.md)）。
   - 或直接由 Agent 手動觸發單次任務：
     ```bash
     python -X utf8 scripts/run_job.py --src "<收件匣子夾路徑>" --agent codex
     ```
6. **讀完 [SKILL.md](SKILL.md) 即可開始幫使用者剪片**！

---

## 📱 使用者三步驟（手機端）

1. **丟素材**：在 OneDrive `手機快剪/收件匣/` 新增任意名稱子夾（如 `陽明山`），放入 5–30 個照片或影片。
2. **講任務單**：在同一夾放入語音備忘（`.m4a` / `.mp3`）或 `任務.txt`，例如：「主題是陽明山，溫馨風格，兩分鐘，直式，女聲」。未指定項目自動套預設（溫馨、90 秒、9:16、男聲、有配樂）。
3. **審台詞 → 領成片**：電腦產生 `_台詞稿.txt` 與 `_分鏡預覽.jpg` 後：
   - 滿意 → 放入檔名「確認」開頭的錄音或文字檔（如 `確認.m4a` / `OK.txt`）
   - 要改 → 放入「修改」開頭的檔案（如「第 3 句改成…」）
   - 確認後約 3–10 分鐘，即可在 `手機快剪/成品/` 取得成片 `.mp4` 與 `.srt` 字幕。

## ☁️ 電腦關機備援（Google Colab）

若電腦未開機，可用手機開啟 `colab/phone_quick_cut.ipynb`（單格一鍵執行到底，從 Google 雲端硬碟讀寫並在結束後自動切斷執行階段）。細節見 [references/colab-fallback.md](references/colab-fallback.md)。
