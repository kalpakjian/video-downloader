"""Smoke and real-download check of the built, windowed Windows executable."""

from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import threading

ROOT = Path(__file__).resolve().parents[1]


def main():
    executable = ROOT / "dist" / "VideoDownloader" / "VideoDownloader.exe"
    subprocess.run([str(executable), "--smoke-test"], check=True, timeout=20)
    source = ROOT / "test-output" / "integration" / "source"
    output = ROOT / "test-output" / "packaged"
    output.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(SimpleHTTPRequestHandler, directory=str(source)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        for profile in ("best", "mp3"):
            report = output / f"{profile}-report.json"
            report.unlink(missing_ok=True)
            subprocess.run([str(executable), "--diagnose-url", f"http://127.0.0.1:{server.server_port}/sample.mp4",
                            "--profile", profile, "--output-dir", str(output / "downloads"), "--report", str(report)],
                           check=True, timeout=45)
            data = json.loads(report.read_text(encoding="utf-8"))
            assert data["success"], data
            paths = [Path(event["path"]) for event in data["events"] if event["type"] == "completed"]
            assert len(paths) == 1 and paths[0].stat().st_size > 0
            assert any(event["type"] == "progress" for event in data["events"]), "No real progress events"
            print("Packaged EXE PASS:", profile, paths[0])
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()