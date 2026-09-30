# 下載影片 — Windows 桌面下載器

繁體中文、無廣告、不需註冊本工具帳號。貼上單支影片網址，將可取得的來源直接存到本機。

## 雙擊啟動

本機專案：`C:\Users\princ\video-downloader`

- 雙擊 `C:\Users\princ\video-downloader\Launch.cmd`。
- 或開啟 `C:\Users\princ\video-downloader\dist\VideoDownloader\VideoDownloader.exe`。
- EXE 使用資料夾式封裝；不要只搬走 EXE，必須保留旁邊的 `_internal` 與 `tools`。
- 目前建置使用本機 PATH 中的 FFmpeg、FFprobe、Node.js，不是完全免相依的可攜版。
- 程式未做商業程式碼簽章，Windows 可能顯示「未知發行者」。請只執行自己建置或確認來源的版本，不必停用防毒。

## 使用方式

1. 貼上完整的 `https://` 單支影片分享網址。
2. 選擇格式，預設為「最高畫質・保留原始編碼」。
3. 選擇儲存位置，預設為 Windows 下載資料夾內的「下載影片」。
4. （選用）在「進階：cookies.txt」填入你自行匯出的 cookies 檔路徑，可下載需登入才能看的內容；留空一律匿名下載。取得方式見下一節。
5. 按「開始下載」，完成後按「開啟資料夾」。
6. 網站改版導致失敗時，可在閒置狀態按「更新下載核心」。

| 選項 | 真正行為 |
| --- | --- |
| 最高畫質 | 使用 yt-dlp 最佳格式排序，最佳影像＋音訊以 MKV 無損合併；單一音畫檔保留來源容器 |
| MP4 相容模式 | 限 H.264 影像＋AAC 音訊，無損合併或重新封裝成 MP4；可能比最高畫質低，沒有相容來源就提示 |
| 1080p 以下 | 嚴格選擇影片高度不超過 1080 的來源，不放大；必要時 MKV |
| 720p 以下 | 嚴格選擇影片高度不超過 720 的來源，不放大；必要時 MKV |
| MP3 音訊 | 最佳可取得音源轉成 MP3 V0；是有損轉換，不會改善音質 |

畫質上限按影片「高度」判斷；直式影片同樣依高度，不以短邊或行銷名稱判斷。直接媒體網址若沒有提供編碼或解析度資訊，相容 MP4／畫質上限模式可能拒絕選取；此時請改用最高畫質。

影像與音訊可能分開下載，各段百分比會重新計算。合併／轉檔階段顯示不定進度，不將下載完成誤報成最終檔案完成。只有核心成功結束且最終檔案確實存在、非空，才標示成功。

## 如何取得 cookies.txt（選用）

部分內容（最常見是 X／Twitter 的敏感或年齡限制貼文）平台只開放給已登入使用者，匿名下載會失敗或顯示「此貼文對未登入訪客隱藏」。此時可提供你自己的登入 cookies：

1. 在 Chrome 安裝開源擴充功能「Get cookies.txt LOCALLY」（[Chrome 商店](https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc)；LOCALLY＝cookie 只在本地匯出，不上傳伺服器）。
2. 先在該瀏覽器**登入目標網站**（例如 x.com）。
3. 停留在該網站頁面上，點擴充功能圖示 → **Export**，取得 `xxx_cookies.txt`。
4. 在本工具第 4 步以「瀏覽…」選擇該檔案後開始下載。

安全須知：

- **cookies.txt 等同你帳號的登入鑰匙**。本工具只在本地把它傳給下載核心，不會上傳、不會存進設定檔（設定只記住檔案路徑）。
- 不要分享該檔案、不要上傳雲端；下載完成後建議刪除。
- Cookie 會過期：若已填了檔案仍失敗，請重新匯出一次。
- 這是給你**用自己的帳號**存取自己可見內容的進階功能，請遵守平台條款。

## 支援與限制

- 核心是 [yt-dlp](https://github.com/yt-dlp/yt-dlp)，主要目標為 YouTube、Instagram、Facebook、X、TikTok 公開單支影片。
- **不保證所有網站或影片成功**。即使公開，平台仍可能要求登入、驗證、特定地區或限制請求。
- 不讀取瀏覽器 Cookie、不收集帳號密碼、不解除 DRM、不繞過付費或私人存取限制。例外：你**明確指定**自行匯出的 cookies.txt 時，僅將該檔案本地傳給下載核心，用於存取你自己帳號可見的內容。
- 第一版不下載播放清單、頻道、多影片貼文、進行中的直播或尚未處理完成的直播。影片網址夾帶清單參數時，只處理該支影片。
- 遇到相同標題、ID 與格式的既有檔案，保留而不覆寫；不同格式使用不同檔名標記。網站之後更新同一 ID 的內容或提高畫質時，請先改用其他資料夾下載。
- 取消／斷線留下的 `.part` 或中間檔會保留以供重試續傳；不會清除資料夾中的其他檔案。
- 「最高畫質」是目前存取條件下平台提供的最佳來源，不是下載不到的原始母帶，也不會放大低畫質。
- 請僅下載自己擁有或獲授權保存的內容，並遵守平台條款與當地法律。

## 相依工具

- 原始碼執行：Python 3.10+，含 Tkinter。介面與控制層只用 Python 標準函式庫。
- yt-dlp：官方 Windows x64 EXE。按更新按鈕可安裝或更新，會驗證 GitHub 官方 release asset 的 SHA-256、檔案大小與版本後才原子替換。
- FFmpeg 與 FFprobe：必須位於相同目錄並加入 PATH，或放在程式旁的 `tools` 資料夾。
- Node.js 22+：YouTube JavaScript 處理所需；會明確傳入 `--js-runtimes node:...`，官方 yt-dlp EXE 已包含配套 EJS。
- 更新不會執行任意遠端 shell，也不載入使用者的 yt-dlp 設定或插件。

原始碼工具路徑：`C:\Users\princ\video-downloader\tools`。

安裝／更新的 yt-dlp 與偏好設定存在 `%LOCALAPPDATA%\VideoDownloader`；在這台電腦通常是 `C:\Users\princ\AppData\Local\VideoDownloader`。設定只保存資料夾、格式，以及 cookies.txt 的**路徑**（檔案本身由你自行管理），不保存影片網址、帳號或歷史紀錄。解析所需的暫存資訊會在工作結束後刪除。畫面中的核心訊息可能包含網址或檔名，分享截圖／紀錄前請自行確認。

## 開發與測試

PowerShell：

```powershell
Set-Location 'C:\Users\princ\video-downloader'
python -m venv 'C:\Users\princ\video-downloader\.venv'
& 'C:\Users\princ\video-downloader\.venv\Scripts\python.exe' 'C:\Users\princ\video-downloader\main.py'
& 'C:\Users\princ\video-downloader\.venv\Scripts\python.exe' -m unittest discover -s 'C:\Users\princ\video-downloader\tests' -v
& 'C:\Users\princ\video-downloader\.venv\Scripts\python.exe' 'C:\Users\princ\video-downloader\main.py' --smoke-test
& 'C:\Users\princ\video-downloader\.venv\Scripts\python.exe' 'C:\Users\princ\video-downloader\scripts\integration_check.py'
& 'C:\Users\princ\video-downloader\.venv\Scripts\python.exe' 'C:\Users\princ\video-downloader\scripts\gui_check.py'
& 'C:\Users\princ\video-downloader\.venv\Scripts\python.exe' 'C:\Users\princ\video-downloader\scripts\cancel_check.py'
& 'C:\Users\princ\video-downloader\.venv\Scripts\python.exe' 'C:\Users\princ\video-downloader\scripts\packaged_check.py'
```

單元測試不連外。整合測試會使用 FFmpeg 自行產生測試音畫，在 127.0.0.1 臨時 HTTP 伺服器供 yt-dlp 下載，再用 FFprobe 驗證；檔案寫入 `C:\Users\princ\video-downloader\test-output`。

`gui_check.py` 測試真正的 Tk 下載工作與完成／取消狀態；`cancel_check.py` 驗證真正的 Windows 子孫程序皆被取消；`packaged_check.py` 在建置完成後測試 EXE 啟動與下載。後兩個 HTTP 介面測試需先執行 `integration_check.py` 產生素材。

診斷模式可透過 EXE 的 `--diagnose-url`、`--output-dir`、`--report` 與選用 `--profile`、`--cookies` 參數執行一次下載，並明確寫入指定 JSON 報告。這是手動啟用的測試功能，報告可能包含網址／檔名，平常桌面操作不會自動保存紀錄。

## 建置 EXE

```powershell
& 'C:\Users\princ\video-downloader\.venv\Scripts\python.exe' -m pip install -r 'C:\Users\princ\video-downloader\requirements-build.txt'
& 'C:\Users\princ\video-downloader\scripts\build.ps1'
```

預設打包 Python／Tk 與 yt-dlp，沿用目的電腦上的 FFmpeg／FFprobe／Node.js。`-IncludeMediaTools` 可額外複製本機這些工具以便本機測試；若要公開散布，請先滿足每項相依元件的授權、對應來源碼與告知義務，尤其本機 FFmpeg full build 的 GPL 元件。參見 `C:\Users\princ\video-downloader\THIRD_PARTY_NOTICES.md`。

## 專案結構

所有下列項目均位於 `C:\Users\princ\video-downloader`：

- `downloader\gui.py`：Tkinter 主執行緒介面、背景工作事件佇列。
- `downloader\engine.py`：格式參數、解析、下載、進度與完成驗證。
- `downloader\processes.py`：Windows Job Object 管理下載與 FFmpeg 子程序。
- `downloader\tools.py`：工具偵測、HTTPS 核心更新與 SHA-256 驗證。
- `downloader\settings.py`：原子保存偏好設定與 Windows 已知下載資料夾。
- `downloader\models.py`：型別、網址驗證與五種格式政策。
- `tests`：不連外的自動化測試。
- `scripts`：整合檢查與打包入口。