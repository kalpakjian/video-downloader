# 驗證結果 — 2026-09-09（本機時間）

## 結論

Windows 桌面版已建立、打包並通過下列實測。這不是「所有社群平台保證成功」的聲明。

| 項目 | 結果 | 證據／範圍 |
| --- | --- | --- |
| 離線單元測試 | **52 / 52 通過** | 網址、格式限制、進度解析、設定保存、更新驗證、取消競態、完成檔案驗證與 Windows Job ABI |
| Tk 啟動 smoke test | 通過 | 原始碼及打包後 EXE 均可建立視窗元件 |
| GUI 真實下載生命週期 | 通過 | 按開始→背景執行→HTTP 下載→完成事件→恢復按鈕；禁止重複啟動 |
| GUI 終態回歸 | 通過 | 下載／更新完成維持 100%；取消歸零；修正 ttk.stop() 重設完成進度問題 |
| 本機 HTTP 單檔 | 通過 | 自製 640×360 H.264＋AAC，3 秒，成功下載 MP4 與轉成 MP3 |
| DASH 最高畫質 | 通過 | 自製分離音畫，選取 1080p，合併 MKV，H.264＋AAC |
| DASH MP4 相容模式 | 通過 | 1080p H.264＋AAC，MP4 無損合併 |
| DASH 1080p 上限 | 通過 | 選取 1080p，MKV |
| DASH 720p 上限 | 通過 | 選取 720p 而非 1080p，MKV |
| DASH MP3 | 通過 | 僅音訊 MP3，約 2 秒 |
| 真正 Windows 子孫程序取消 | 通過 | 啟動 Python 父／子程序，取消後皆退出，無完成事件、無殘留引擎狀態；最後重跑約 0.078 秒 |
| 官方核心安裝／更新 | 通過 | yt-dlp 2026.08.19，官方 release API SHA-256、大小與執行版本驗證 |
| 公開 HTTPS 影片 | 通過 | Blender Big Buck Bunny 預告片，720×400 Theora＋Vorbis、約 32.997 秒、4,360,399 bytes |
| 打包後 EXE 實際下載 | 通過 | 獨立 EXE 下载本機 HTTP MP4、轉 MP3，存在真實進度事件，最終非空檔案 |
| YouTube | **本次未成功** | 測試連結 `https://www.youtube.com/watch?v=BaW_jenozKc` 回覆 `This video is unavailable`；不推論所有 YouTube 網址失效或成功 |
| Instagram／Facebook／X／TikTok | **未實測** | 沿用 yt-dlp 支援，未提供實際授權測試網址；不標為通過 |

自製測試素材由 FFmpeg lavfi 產生；不需要社群帳號。公開素材的授權與署名記載於 `C:\Users\princ\video-downloader\THIRD_PARTY_NOTICES.md`。

## 成品

- 啟動入口：`C:\Users\princ\video-downloader\Launch.cmd`
- 執行檔：`C:\Users\princ\video-downloader\dist\VideoDownloader\VideoDownloader.exe`
- EXE SHA-256：`9D3B7688BA8FF0D4CF6DDC253B7384DFBF45B36630AA2578BF9F70B3AFD3310B`
- 整個資料夾約 47 MiB，Python／Tk 與官方 yt-dlp 已打包；沿用本機 FFmpeg／FFprobe／Node.js，不是完全獨立可攜包。
- Python 3.11.15、Tk/Tcl 8.6.12、FFmpeg/FFprobe 8.1、Node.js 24.14.1、PyInstaller 6.22.0。
- PyInstaller 警告已檢查，為其他作業系統或選用模組；EXE 啟動與下載實測通過。

## 重現與紀錄

請參照 `C:\Users\princ\video-downloader\README.md` 中的測試命令。

- 媒體整合報告：`C:\Users\princ\video-downloader\test-output\integration\results.json`
- 打包執行報告：`C:\Users\princ\video-downloader\test-output\packaged\best-report.json` 與 `C:\Users\princ\video-downloader\test-output\packaged\mp3-report.json`
- 建置紀錄：`C:\Users\princ\video-downloader\test-output\build.stdout.log`、`C:\Users\princ\video-downloader\test-output\build.stderr.log`

核心更新的取消會等待目前網路讀取／驗證逾時（網路 20 秒、版本檢查 30 秒）；介面會保持可回應。下載取消使用 Windows Job Object 同時終止本次子孫程序，保留可續傳中間檔案。