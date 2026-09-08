"""Exercise the actual Tk start/worker/completion flow against local HTTP media."""

from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys
import threading
import time
import tkinter as tk
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from downloader.gui import DownloaderApp


def main():
    source = ROOT / "test-output" / "integration" / "source"
    assert (source / "sample.mp4").is_file(), "Run integration_check.py first"
    output = ROOT / "test-output" / "gui"
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(SimpleHTTPRequestHandler, directory=str(source)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    root = tk.Tk()
    root.withdraw()
    app = None
    errors = []
    try:
        with patch("downloader.gui.save_settings"), patch("downloader.gui.messagebox.showerror", side_effect=lambda *a, **k: errors.append(a)):
            app = DownloaderApp(root)
            app.url.set(f"http://127.0.0.1:{server.server_port}/sample.mp4")
            app.folder.set(str(output))
            app.start_download()
            assert app.worker is not None
            assert app.start_button.instate(["disabled"])
            first_worker = app.worker
            app.start_download()
            assert app.worker is first_worker, "Duplicate job started"
            end = time.monotonic() + 45
            while app.worker is not None and time.monotonic() < end:
                root.update()
                time.sleep(0.02)
            assert app.worker is None, "GUI download timeout"
            assert not errors, errors
            assert app.last_path and app.last_path.is_file()
            assert app.progress["value"] == 100
            assert app.start_button.instate(["!disabled"])
            assert app.cancel_button.instate(["disabled"])
            assert "下載完成" in app.status.get()
            print("GUI download lifecycle PASS:", app.last_path)
            # Simulate terminal update/cancel events and worker exit. Regression:
            # polling must preserve the final 100% progress indicator.
            from unittest.mock import Mock
            for event, expected in (({"type": "updated", "version": "test"}, 100),
                                    ({"type": "cancelled", "message": "test cancel"}, 0)):
                app.worker = Mock()
                app.worker.is_alive.return_value = False
                app.events.put(event)
                app.events.put({"type": "finished"})
                deadline = time.monotonic() + 2
                while app.worker is not None and time.monotonic() < deadline:
                    root.update()
                    time.sleep(0.02)
                assert app.worker is None
                assert app.progress["value"] == expected
            print("GUI update/cancel terminal-state regression PASS")
    finally:
        if app is not None:
            if app.worker is not None:
                app.cancel()
                app.worker.join(timeout=15)
            app.destroy()
        else:
            root.destroy()
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()