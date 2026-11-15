# Colab 備援（電腦關機時）

## 2026-11-15 手機實測教訓

- 手機瀏覽器一切到別的 App、關螢幕或換網路，就和 Colab 斷線（`await connected: disconnected`），出現「正在連線」卡住。
- 舊版逐格執行＋`files.upload()`／`files.download()` 都要手機一直連著 → 必卡；斷線後也看不出機器有沒有關。
- 因此改成**單一儲存格**：按一次 ▶，雲端自己跑完；素材與成果都在 Google 雲端硬碟；`try/finally` 保證關機。

## 準備（電腦，已完成）

- notebook：`G:\我的雲端硬碟\Colab\phone_quick_cut.ipynb`（改任何腳本後跑 `make_colab_nb.py --copy-to-gdrive` 同步）
- 素材放雲端硬碟任一資料夾，例如 `手機快剪/收件匣/<名稱>`（Google 相簿「分享 → 雲端硬碟」或雲端硬碟 App「上傳」）

## 手機操作

1. 雲端硬碟 App → `Colab/phone_quick_cut.ipynb` →「透過 Colab 開啟」。
2. 表單：`雲端硬碟資料夾` 填素材夾路徑；`階段` 先選「出台詞稿（先審）」；主題、風格、長度、比例、聲音。
3. 按儲存格左邊 ▶ **一次**，第一次授權按「允許」，之後可以關螢幕。
4. 約 5–8 分鐘後，在雲端硬碟該資料夾看 `_狀態.txt`：
   - `待審閱（Colab）`：看 `_台詞稿.txt`、`_分鏡預覽.jpg`。要改台詞就編輯 `_script.json` 的 `narration`（或改表單重出）。
   - 沒問題 → 回 notebook 把 `階段` 改「台詞已確認，合成」再按 ▶ 一次，約 8–15 分鐘後成片在 `成品/`。
   - `失敗（Colab）`：看 `_colab_log.txt` 最後幾行，截圖給 agent。
5. 每一次執行最後都會 `runtime.unassign()` 自動關機。

## 確認有沒有關機

- 手機：colab.research.google.com → 右上「⋮」→「管理工作階段」，清單空白＝已關。
- 電腦：`py -3 -X utf8 D:\secondbrain\協作工程\_tools\colab\colab_guard.py check`，`Active assignments: 0`＝已關。瀏覽器開的機器 CLI 關不掉，只能從網頁「中斷連線並刪除執行階段」。

## 和電腦版的差別

| 項目 | 電腦版 | Colab 版 |
|---|---|---|
| 寫腳本 | Codex／Claude 看接觸表寫 | Colab AI 只讀文字（看不到畫面）；失敗用 template |
| 配樂 | Lyria | MusicGen-small（CPU 約 1–3 分鐘） |
| 審閱 | 收件匣放「確認」／「修改」檔 | 改表單「階段」再按一次 ▶ |
| 現場講話 | 會轉逐字稿 | 略過（省時間） |

## 實測紀錄（2026-11-15，Galaxy Z Fold8＋Chrome）

- 單格版成功：授權後約 4 分鐘出 21 秒成片（5 個素材），最後 `Active assignments: 0` 確認已關機。
- **授權前螢幕不能暗**：`drive.mount` 等「允許」時螢幕關掉會一直卡住（雲端硬碟沒有任何 `_狀態.txt`）。看到「安裝工具…」後才可關螢幕；之後全在雲端跑，斷線不影響。
- Colab AI 只看文字、看不到畫面，會編出畫面沒有的情節（「三袋戰利品」）且偏幽默誇張；重要的片仍以電腦版為準，或務必走「出台詞稿」先審。
- 素材少時成片會遠短於目標長度（5 個素材 → 21 秒）。
