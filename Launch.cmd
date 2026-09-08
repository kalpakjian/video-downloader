@echo off
setlocal
cd /d "%~dp0"
if exist "%~dp0dist\VideoDownloader\VideoDownloader.exe" (
    start "" "%~dp0dist\VideoDownloader\VideoDownloader.exe"
    exit /b 0
)
if exist "%~dp0.venv\Scripts\pythonw.exe" (
    start "" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0main.py"
    exit /b 0
)
echo Python environment not found. Please follow README.md to set up this app.
exit /b 1