"""Global hotkey on Windows via RegisterHotKey; stdlib only, no extra deps."""

import ctypes
from ctypes import wintypes
import threading

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
WM_HOTKEY = 0x0312
WM_QUIT = 0x0012


class _MSG(ctypes.Structure):
    _fields_ = [("hwnd", wintypes.HWND), ("message", wintypes.UINT),
                ("wParam", wintypes.WPARAM), ("lParam", wintypes.LPARAM),
                ("time", wintypes.DWORD), ("pt", wintypes.POINT)]


class GlobalHotkey:
    """Register a system-wide hotkey and invoke a callback whenever pressed.

    The callback fires on the hotkey's own daemon thread — dispatch to the UI
    thread (e.g. via a thread-safe queue) yourself.
    """

    def __init__(self, modifiers: int, vk: int, callback):
        self._modifiers = modifiers
        self._vk = vk
        self._callback = callback
        self._id = 0xB001
        self._thread = None
        self._ready = threading.Event()
        self.failed = False

    def start(self) -> bool:
        if self._thread is not None:
            return not self.failed
        self._ready.clear()
        self._thread = threading.Thread(target=self._run, name="video-downloader-hotkey", daemon=True)
        self._thread.start()
        self._ready.wait(timeout=5)
        return not self.failed

    def _run(self):
        user32 = ctypes.windll.user32
        if not user32.RegisterHotKey(None, self._id, self._modifiers, self._vk):
            self.failed = True
            self._ready.set()
            return
        self._ready.set()
        msg = _MSG()
        while True:
            # GetMessageW blocks until a hotkey or WM_QUIT arrives for this thread.
            result = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
            if result in (0, -1):  # WM_QUIT or error
                break
            if msg.message == WM_HOTKEY and msg.wParam == self._id:
                try:
                    self._callback()
                except Exception:
                    pass
        user32.UnregisterHotKey(None, self._id)

    def stop(self) -> None:
        thread = self._thread
        if thread is None or not thread.is_alive():
            return
        ctypes.windll.user32.PostThreadMessageW(thread.ident, WM_QUIT, 0, 0)
        thread.join(timeout=2)
