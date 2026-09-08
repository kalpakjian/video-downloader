"""Offline Windows integration check: real Job Object descendant cancellation."""

import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from downloader.engine import DownloadEngine
from downloader.models import DownloadCancelled


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def main():
    require(os.name == "nt", "This check requires Windows")
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel.GetExitCodeProcess.restype = wintypes.BOOL
    kernel.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel.TerminateProcess.restype = wintypes.BOOL
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL

    def active(handle):
        code = wintypes.DWORD()
        if not kernel.GetExitCodeProcess(handle, ctypes.byref(code)):
            raise ctypes.WinError(ctypes.get_last_error())
        return code.value == 259  # STILL_ACTIVE

    events = []
    early = DownloadEngine(events.append)
    early.cancel()
    with patch("downloader.engine.subprocess.Popen") as launch:
        try:
            early._execute([sys.executable, "-c", "raise SystemExit(99)"], lambda line: None)
        except DownloadCancelled:
            pass
        else:
            raise AssertionError("Pre-start cancellation was not raised")
        launch.assert_not_called()
    require(early._process is None and early._job is None, "Pre-start state leaked")

    engine = DownloadEngine(events.append)
    handles, parents, pids = [], [], []
    watchdog_fired = threading.Event()
    def watchdog():
        watchdog_fired.set()
        engine.cancel()
        process = engine._process
        if process is not None and process.poll() is None:
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                           capture_output=True, timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)

    def consume(line):
        require(line.startswith("CHILD:"), f"Unexpected subprocess output: {line}")
        pid = int(line.split(":", 1)[1])
        pids.append(pid)
        handle = kernel.OpenProcess(0x1000 | 0x00100000 | 0x0001, False, pid)
        if not handle:
            raise ctypes.WinError(ctypes.get_last_error())
        handles.append(handle)  # Hold handle to prevent PID reuse ambiguity.
        parents.append(engine._process)
        require(active(handle), "Descendant exited before cancellation")
        engine.cancel()

    code = ("import subprocess,sys,time; "
            "child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)']); "
            "print('CHILD:'+str(child.pid),flush=True); time.sleep(30)")
    timer = threading.Timer(8, watchdog)
    timer.daemon = True
    started = time.monotonic()
    timer.start()
    try:
        try:
            engine._execute([sys.executable, "-u", "-c", code], consume)
        except DownloadCancelled:
            pass
        else:
            raise AssertionError("Running cancellation was not raised")
        require(len(handles) == 1, "No descendant was observed")
        require(kernel.WaitForSingleObject(handles[0], 3000) == 0, "Descendant survived cancellation")
        require(not active(handles[0]), "Descendant remains active")
        require(parents[0].poll() is not None, "Parent remains active")
        require(engine._process is None and engine._job is None, "Engine state leaked")
        require(not any(event.get("type") == "completed" for event in events), "False completion")
        elapsed = time.monotonic() - started
        require(elapsed < 8 and not watchdog_fired.is_set(), "Cancellation exceeded time bound")
        print(f"PASS: pre-start no launch; real parent/child {pids[0]} exited; "
              f"no completion; state cleared; elapsed={elapsed:.3f}s")
    finally:
        timer.cancel()
        engine.cancel()
        for handle in handles:
            try:
                if active(handle):
                    kernel.TerminateProcess(handle, 1)
                    require(kernel.WaitForSingleObject(handle, 5000) == 0, "Fallback cleanup failed")
            finally:
                kernel.CloseHandle(handle)
        for process in parents:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=5)


if __name__ == "__main__":
    main()