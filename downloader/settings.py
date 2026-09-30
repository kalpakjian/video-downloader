"""Small atomic settings file; never store URLs, history, or credential material.

cookies_file 只是一個指向使用者自行管理之 cookies.txt 的路徑，設定檔本身不含任何憑證。
"""

import json
import os
from pathlib import Path
import tempfile

from .models import PROFILE_BY_ID


def data_dir() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local")) / "VideoDownloader"


def default_download_dir() -> Path:
    # Windows Known Folder API respects redirected Downloads folders.
    if os.name == "nt":
        import ctypes
        import uuid
        from ctypes import wintypes

        folder_id = (ctypes.c_ubyte * 16).from_buffer_copy(
            uuid.UUID("374de290-123f-4565-9164-39c4925e467b").bytes_le)
        result = ctypes.c_wchar_p()
        shell = ctypes.WinDLL("shell32")
        shell.SHGetKnownFolderPath.argtypes = [ctypes.c_void_p, wintypes.DWORD, wintypes.HANDLE,
                                                ctypes.POINTER(ctypes.c_wchar_p)]
        shell.SHGetKnownFolderPath.restype = ctypes.c_long
        if shell.SHGetKnownFolderPath(ctypes.byref(folder_id), 0, None, ctypes.byref(result)) == 0:
            try:
                return Path(result.value) / "下載影片"
            finally:
                ole = ctypes.WinDLL("ole32")
                ole.CoTaskMemFree.argtypes = [ctypes.c_void_p]
                ole.CoTaskMemFree(ctypes.cast(result, ctypes.c_void_p))
    return Path.home() / "Downloads" / "下載影片"


def load_settings() -> dict[str, str]:
    defaults = {"output_dir": str(default_download_dir()), "profile": "best", "cookies_file": ""}
    try:
        raw = json.loads((data_dir() / "settings.json").read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            folder = raw.get("output_dir")
            if isinstance(folder, str) and folder and "\x00" not in folder and Path(folder).is_absolute():
                defaults["output_dir"] = folder
            if isinstance(raw.get("profile"), str) and raw["profile"] in PROFILE_BY_ID:
                defaults["profile"] = raw["profile"]
            cookies = raw.get("cookies_file")
            if isinstance(cookies, str) and cookies and "\x00" not in cookies:
                defaults["cookies_file"] = cookies
    except (OSError, ValueError, TypeError):
        pass
    return defaults


def save_settings(settings: dict[str, str]) -> None:
    payload = {"output_dir": str(settings["output_dir"]), "profile": settings["profile"],
               "cookies_file": str(settings.get("cookies_file", ""))}
    root = data_dir()
    root.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix="settings-", suffix=".tmp", dir=root)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        os.replace(temp, root / "settings.json")
    finally:
        Path(temp).unlink(missing_ok=True)