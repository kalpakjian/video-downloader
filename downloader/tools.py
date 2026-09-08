"""Discover local executables and atomically update the official download core."""

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from urllib.request import Request, urlopen

from .models import DownloadCancelled, DownloadError
from .settings import data_dir

RELEASE_API = "https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest"
MAX_CORE_BYTES = 100 * 1024 * 1024


def app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def hidden_process_options() -> dict:
    return {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}


class ToolManager:
    def __init__(self):
        self._cancel = threading.Event()

    def status(self) -> dict[str, str | None]:
        results = {}
        for key, filename in (("yt_dlp", "yt-dlp.exe"), ("ffmpeg", "ffmpeg.exe"),
                              ("ffprobe", "ffprobe.exe"), ("node", "node.exe")):
            candidates = []
            if key == "yt_dlp":
                candidates.append(data_dir() / "tools" / filename)
            candidates.extend((app_dir() / "tools" / filename, app_dir() / filename))
            found = next((str(path) for path in candidates if path.is_file()), None)
            # Never automatically execute an arbitrary yt-dlp from PATH.
            if found is None and key != "yt_dlp":
                found = shutil.which(filename)
            results[key] = found
        return results

    def cancel_update(self) -> None:
        self._cancel.set()

    def _check_cancel(self) -> None:
        if self._cancel.is_set():
            raise DownloadCancelled("已取消更新；原有下載核心保持不變。")

    def update_core(self, emit) -> str:
        # A manager is created for each operation: do not clear an early cancel.
        temp_path = None
        try:
            self._check_cancel()
            emit({"type": "status", "message": "正在查詢官方下載核心版本…"})
            headers = {"User-Agent": "VideoDownloader/1.0", "Accept": "application/vnd.github+json"}
            with urlopen(Request(RELEASE_API, headers=headers), timeout=20) as response:
                raw = response.read(2 * 1024 * 1024 + 1)
            if len(raw) > 2 * 1024 * 1024:
                raise DownloadError("官方版本資訊異常，更新已中止。")
            metadata = json.loads(raw)
            version = metadata["tag_name"]
            if not re.fullmatch(r"\d{4}\.\d{2}\.\d{2}(?:\.\d+)?", version):
                raise DownloadError("官方版本號格式不符，更新已中止。")
            asset = next(item for item in metadata["assets"] if item["name"] == "yt-dlp.exe")
            expected_url = f"https://github.com/yt-dlp/yt-dlp/releases/download/{version}/yt-dlp.exe"
            digest = asset.get("digest", "")
            if asset["browser_download_url"] != expected_url or not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
                raise DownloadError("官方下載網址或 SHA-256 驗證資訊不符，更新已中止。")
            expected_size = asset["size"]
            if not isinstance(expected_size, int) or not 0 < expected_size <= MAX_CORE_BYTES:
                raise DownloadError("下載核心檔案大小異常。")
            self._check_cancel()
            destination = data_dir() / "tools"
            destination.mkdir(parents=True, exist_ok=True)
            fd, name = tempfile.mkstemp(prefix="yt-dlp-", suffix=".exe", dir=destination)
            temp_path = Path(name)
            emit({"type": "log", "message": f"下載官方 yt-dlp {version}，完成後驗證 SHA-256。"})
            hasher = hashlib.sha256()
            received = 0
            with os.fdopen(fd, "wb") as output:
                with urlopen(Request(expected_url, headers={"User-Agent": "VideoDownloader/1.0"}), timeout=20) as response:
                    while True:
                        self._check_cancel()
                        block = response.read(256 * 1024)
                        if not block:
                            break
                        received += len(block)
                        if received > expected_size:
                            raise DownloadError("下載大小超出預期，更新已中止。")
                        hasher.update(block)
                        output.write(block)
                        emit({"type": "progress", "percent": received * 100 / expected_size,
                              "speed": "", "eta": "", "phase": "download"})
            self._check_cancel()
            if received != expected_size or hasher.hexdigest() != digest.split(":", 1)[1]:
                raise DownloadError("SHA-256 或大小驗證失敗；未替換原有核心，請稍後重試。")
            check = subprocess.run([str(temp_path), "--ignore-config", "--version"], capture_output=True,
                                   text=True, encoding="utf-8", errors="replace", timeout=30,
                                   **hidden_process_options())
            self._check_cancel()
            if check.returncode != 0 or check.stdout.strip() != version:
                raise DownloadError("新核心無法正常執行；原有核心保持不變。")
            os.replace(temp_path, destination / "yt-dlp.exe")
            emit({"type": "log", "message": f"核心 {version} 已通過 SHA-256 與啟動驗證。"})
            return version
        except DownloadError:
            raise
        except Exception as exc:
            if self._cancel.is_set():
                raise DownloadCancelled("已取消核心更新。") from exc
            raise DownloadError(f"核心更新失敗：{exc}\n請確認能連線 GitHub、磁碟可寫入，並稍後重試。") from exc
        finally:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)