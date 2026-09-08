"""Opt-in real HTTP + FFmpeg end-to-end checks, using self-generated media.

Run from the project root: .venv\Scripts\python.exe scripts\integration_check.py
No social account, copyrighted sample, or external website is required.
"""

from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import subprocess
import sys
import threading

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from downloader.engine import DownloadEngine
from downloader.models import DownloadRequest
from downloader.tools import ToolManager, hidden_process_options


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def main():
    tools = ToolManager().status()
    folder = ROOT / "test-output" / "integration"
    source = folder / "source"
    source.mkdir(parents=True, exist_ok=True)
    subprocess.run([tools["ffmpeg"], "-hide_banner", "-loglevel", "error", "-y",
                    "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=24",
                    "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100",
                    "-t", "3", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
                    "-movflags", "+faststart", str(source / "sample.mp4")], check=True,
                   **hidden_process_options())
    # DASH publishes real codec / resolution metadata and separate video/audio.
    subprocess.run([tools["ffmpeg"], "-hide_banner", "-loglevel", "error", "-y",
                    "-f", "lavfi", "-i", "testsrc2=size=1920x1080:rate=24",
                    "-f", "lavfi", "-i", "sine=frequency=660:sample_rate=44100",
                    "-t", "2", "-map", "0:v", "-map", "0:v", "-map", "1:a",
                    "-filter:v:1", "scale=1280:720", "-c:v", "libx264", "-preset", "ultrafast",
                    "-pix_fmt", "yuv420p", "-g", "24", "-keyint_min", "24", "-sc_threshold", "0",
                    "-b:v:0", "1600k", "-b:v:1", "800k", "-c:a", "aac", "-b:a", "96k",
                    "-use_template", "1", "-use_timeline", "1", "-adaptation_sets",
                    "id=0,streams=v id=1,streams=a", "-f", "dash", "stream.mpd"],
                   check=True, cwd=source, **hidden_process_options())
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=str(source)))
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    summaries = []
    try:
        url = f"http://127.0.0.1:{server.server_port}/sample.mp4"
        # A direct HTTP source does not publish codec/height metadata; test best
        # and MP3 here. Separate info-json fixture checks exercise other selectors.
        for profile in ("best", "mp3"):
            events = []

            def emit(event):
                events.append(event)
                if event["type"] in {"status", "completed", "log"}:
                    print(event, flush=True)

            DownloadEngine(emit).run(DownloadRequest(url, folder / "downloads", profile))
            outputs = [Path(event["path"]) for event in events if event["type"] == "completed"]
            assert len(outputs) == 1, outputs
            result = subprocess.run([tools["ffprobe"], "-v", "error", "-show_streams", "-show_format",
                                     "-of", "json", str(outputs[0])], check=True, capture_output=True,
                                    text=True, encoding="utf-8", **hidden_process_options())
            media = json.loads(result.stdout)
            kinds = {stream["codec_type"] for stream in media["streams"]}
            assert "audio" in kinds
            if profile == "best":
                assert "video" in kinds
                video = next(stream for stream in media["streams"] if stream["codec_type"] == "video")
                assert (video["width"], video["height"]) == (640, 360)
            else:
                assert kinds == {"audio"}
                assert media["streams"][0]["codec_name"] == "mp3"
            assert 2.5 <= float(media["format"]["duration"]) <= 3.5
            summaries.append({"profile": profile, "path": str(outputs[0]), "streams": sorted(kinds),
                              "duration": media["format"]["duration"]})
        dash_url = f"http://127.0.0.1:{server.server_port}/stream.mpd"
        for profile in ("best", "mp4", "1080p", "720p", "mp3"):
            events = []
            def dash_emit(event):
                events.append(event)
                if event["type"] == "log":
                    print(event["message"], flush=True)
            DownloadEngine(dash_emit).run(DownloadRequest(dash_url, folder / "dash-downloads", profile))
            outputs = [Path(e["path"]) for e in events if e["type"] == "completed"]
            assert len(outputs) == 1
            result = subprocess.run([tools["ffprobe"], "-v", "error", "-show_streams", "-show_format",
                                     "-of", "json", str(outputs[0])], check=True, capture_output=True,
                                    text=True, encoding="utf-8", **hidden_process_options())
            media = json.loads(result.stdout)
            kinds = {s["codec_type"] for s in media["streams"]}
            assert "audio" in kinds
            if profile == "mp3":
                assert kinds == {"audio"}
                assert media["streams"][0]["codec_name"] == "mp3"
                height = None
            else:
                video = next(s for s in media["streams"] if s["codec_type"] == "video")
                height = video["height"]
                assert height == (720 if profile == "720p" else 1080), (profile, height)
                assert video["codec_name"] == "h264"
                assert next(s for s in media["streams"] if s["codec_type"] == "audio")["codec_name"] == "aac"
                assert outputs[0].suffix == (".mp4" if profile == "mp4" else ".mkv")
            summaries.append({"profile": "dash-" + profile, "height": height, "path": str(outputs[0]),
                              "streams": sorted(kinds), "duration": media["format"]["duration"]})
            print("DASH PASS:", summaries[-1], flush=True)
        (folder / "results.json").write_text(json.dumps(summaries, indent=2), encoding="utf-8")
        print("PASS:", json.dumps(summaries), flush=True)
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)


if __name__ == "__main__":
    main()