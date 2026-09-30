"""Core contract tests; never use the network or launch downloaded executables."""

import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

from downloader import engine, models, processes, settings, tools


TOOL_PATHS = {
    "yt_dlp": r"C:\tools\yt-dlp.exe",
    "ffmpeg": r"C:\tools\ffmpeg.exe",
    "ffprobe": r"C:\tools\ffprobe.exe",
    "node": r"C:\tools\node.exe",
}


class ModelTests(unittest.TestCase):
    def test_valid_urls_preserve_query_and_trim_edges(self):
        for url in ("https://example.com/watch?v=a&x=b", "http://localhost:8080/a",
                    "https://[::1]/a", "HTTPS://example.com/video"):
            with self.subTest(url=url):
                self.assertEqual(models.validate_url("  " + url + "\n"), url)

    def test_invalid_urls(self):
        values = ("", "   ", "example.com", "file:///C:/video.mp4", "javascript:alert(1)",
                  "ftp://example.com/a", "https:///missing", "--exec=calc", "https://a/b c",
                  "https://a/b\nc", "https://a/\x00x", "https://a/\x7fx", "https://a:0/",
                  "https://a:99999/", "https://a:port/", "https://[broken/", "https://a\\b/",
                  "https://user@example.com/", "https://user:pass@example.com/",
                  "https://example.com/" + "x" * 8192)
        for value in values:
            with self.subTest(value=value[:80]), self.assertRaises(models.DownloadError):
                models.validate_url(value)

    def test_profiles_have_unique_ids_and_no_video_upscaling(self):
        self.assertEqual(len(models.PROFILES), len(models.PROFILE_BY_ID))
        for profile in models.PROFILES:
            with self.subTest(profile=profile.id):
                args = engine.build_common_args(models.DownloadRequest("https://example.com/v", Path.cwd(), profile.id), TOOL_PATHS)
                self.assertEqual(args[args.index("--format") + 1], profile.selector)
                combined = " ".join(args + list(profile.extra_args))
                for forbidden in ("--recode-video", "--postprocessor-args", "scale=", "--exec", "--no-check-certificates"):
                    self.assertNotIn(forbidden, combined)
                self.assertIn("--ignore-config", args)
                self.assertIn("--no-playlist", args)
                self.assertIn("--no-plugin-dirs", args)

    def test_resolution_caps_apply_to_every_fallback(self):
        for height in (720, 1080):
            selector = models.PROFILE_BY_ID[f"{height}p"].selector
            for fallback in selector.split("/"):
                self.assertIn(f"[height<={height}]", fallback)

    def test_mp4_is_codec_constrained_and_mp3_explicitly_extracts(self):
        profile = models.PROFILE_BY_ID["mp4"]
        for fallback in profile.selector.split("/"):
            self.assertIn("avc1|h264", fallback)
            self.assertIn("mp4a|aac", fallback)
        self.assertIn("--remux-video", profile.extra_args)
        self.assertIn("--extract-audio", models.PROFILE_BY_ID["mp3"].extra_args)

    def test_missing_tools_and_unknown_profile(self):
        request = models.DownloadRequest("https://example.com/v", Path.cwd())
        for key in ("yt_dlp", "ffmpeg", "ffprobe"):
            with self.subTest(key=key), self.assertRaises(models.DownloadError):
                engine.build_common_args(request, {**TOOL_PATHS, key: None})
        with self.assertRaises(models.DownloadError):
            engine.build_common_args(models.DownloadRequest(request.url, request.output_dir, "invalid"), TOOL_PATHS)

    def test_cookie_file_arg_added_when_present_and_validated(self):
        with tempfile.TemporaryDirectory() as tmp:
            cookie = Path(tmp) / "cookies.txt"
            cookie.write_text("# Netscape HTTP Cookie File\n", encoding="utf-8")
            args = engine.build_common_args(models.DownloadRequest("https://example.com/v", Path.cwd(), "best", str(cookie)), TOOL_PATHS)
            self.assertEqual(args[args.index("--cookies") + 1], str(cookie))
        with self.subTest(missing="不存在檔案"), self.assertRaises(models.DownloadError):
            engine.build_common_args(models.DownloadRequest("https://example.com/v", Path.cwd(), "best",
                                                            str(Path("missing") / "cookies.txt")), TOOL_PATHS)
        with self.subTest(missing="相對路徑"), self.assertRaises(models.DownloadError):
            engine.build_common_args(models.DownloadRequest("https://example.com/v", Path.cwd(), "best", "cookies.txt"), TOOL_PATHS)
        self.assertNotIn("--cookies", engine.build_common_args(models.DownloadRequest("https://example.com/v", Path.cwd()), TOOL_PATHS))

    def test_youtube_requires_node_other_sites_do_not(self):
        available = {**TOOL_PATHS, "node": None}
        with self.assertRaises(models.DownloadError):
            engine.build_common_args(models.DownloadRequest("https://youtu.be/example", Path.cwd()), available)
        self.assertNotIn("--js-runtimes", engine.build_common_args(models.DownloadRequest("https://example.com/v", Path.cwd()), available))


class EventTests(unittest.TestCase):
    def test_valid_progress(self):
        event = engine.parse_event('VD_PROGRESS:{"downloaded_bytes":512,"total_bytes":1024,"speed":2048,"eta":65}')
        self.assertEqual(event, {"type": "progress", "percent": 50.0, "speed": "2.0 KiB/s", "eta": "01:05", "phase": "download"})

    def test_estimated_total_and_clamped_percentage(self):
        event = engine.parse_event('VD_PROGRESS:{"downloaded_bytes":20,"total_bytes_estimate":10}')
        self.assertEqual(event["percent"], 100.0)

    def test_missing_progress_data(self):
        self.assertEqual(engine.parse_event("VD_PROGRESS:{}"),
                         {"type": "progress", "percent": None, "speed": "", "eta": "", "phase": "download"})

    def test_malformed_and_unmarked_lines(self):
        for line in ("", "[download] 100%", 'prefix VD_PROGRESS:{}', "VD_PROGRESS:{bad", "VD_PROGRESS:[]",
                     "VD_PROGRESS:null", "VD_POST:true", "VD_FILE:bad", 'VD_FILE:""', "VD_FILE:123"):
            with self.subTest(line=line):
                self.assertIsNone(engine.parse_event(line))

    def test_nonfinite_negative_bool_and_nonnumeric_progress(self):
        for value in (float("nan"), float("inf"), float("-inf"), -1, True, "NaN", "invalid", None):
            with self.subTest(value=value):
                event = engine.parse_event("VD_PROGRESS:" + json.dumps(dict(downloaded_bytes=value, total_bytes=100, speed=value, eta=value)))
                self.assertIsNone(event["percent"])
                self.assertEqual(event["speed"], "")
                self.assertEqual(event["eta"], "")

    def test_huge_integer_progress_is_ignored(self):
        event = engine.parse_event("VD_PROGRESS:" + json.dumps({"downloaded_bytes": 10 ** 400, "total_bytes": 10}))
        self.assertIsNone(event["percent"])

    def test_zero_total_is_indeterminate(self):
        self.assertIsNone(engine.parse_event('VD_PROGRESS:{"downloaded_bytes":0,"total_bytes":0}')["percent"])

    def test_postprocessing_does_not_claim_completion(self):
        event = engine.parse_event('VD_POST:{"downloaded_bytes":10,"total_bytes":10}')
        self.assertEqual(event["phase"], "processing")
        self.assertEqual(event["type"], "progress")
        self.assertIsNone(event["percent"])

    def test_completed_path_is_json_decoded(self):
        path = r"C:\下載\影片.mkv"
        self.assertEqual(engine.parse_event("VD_FILE:" + json.dumps(path)), {"type": "completed", "path": path})

    def test_speed_units(self):
        for value, expected in ((0, "0.0 B/s"), (1024, "1.0 KiB/s"), (1024 ** 2, "1.0 MiB/s"), (1024 ** 3, "1.0 GiB/s")):
            with self.subTest(value=value):
                self.assertEqual(engine.format_speed(value), expected)

    def test_friendly_errors(self):
        cases = (("No video could be found in this tweet", "敏感"), ("TweetTombstone", "敏感"),
                 ("SIGN IN required", "登入"), ("DRM protected", "DRM"), ("not available in your country", "地區"),
                 ("requested format unavailable", "畫質"), ("Unsupported URL", "不受"), ("429 Too Many Requests", "頻率"),
                 ("403 Forbidden", "403"), ("Connection timed out", "HTTPS"), ("No space left", "空間"),
                 ("Access is denied", "寫入"), ("404 not found", "移除"), ("unexpected failure", "下載失敗"))
        for message, expected in cases:
            with self.subTest(message=message):
                self.assertIn(expected, engine.friendly_error(message))
        self.assertIn("H.264", engine.friendly_error("requested format unavailable", "mp4"))


class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.default = self.root / "downloads"
        self.addCleanup(patch.stopall)
        patch.object(settings, "data_dir", return_value=self.root).start()
        patch.object(settings, "default_download_dir", return_value=self.default).start()

    def test_missing_settings_defaults(self):
        self.assertEqual(settings.load_settings(), {"output_dir": str(self.default), "profile": "best", "cookies_file": ""})

    def test_corrupt_and_wrong_shape_defaults(self):
        for content in ("not json", "[]", "null", '"text"', "{", '{"profile":[],"output_dir":42}'):
            with self.subTest(content=content):
                (self.root / "settings.json").write_text(content, encoding="utf-8")
                self.assertEqual(settings.load_settings(), {"output_dir": str(self.default), "profile": "best", "cookies_file": ""})

    def test_invalid_fields_are_ignored_independently(self):
        for folder in ("relative", "", "bad\x00path"):
            (self.root / "settings.json").write_text(json.dumps({"output_dir": folder, "profile": "720p"}), encoding="utf-8")
            self.assertEqual(settings.load_settings(), {"output_dir": str(self.default), "profile": "720p", "cookies_file": ""})

    def test_cookie_path_roundtrip(self):
        path = str(self.root / "cookies.txt")
        settings.save_settings({"output_dir": str(self.default), "profile": "best", "cookies_file": path})
        self.assertEqual(settings.load_settings()["cookies_file"], path)
        (self.root / "settings.json").write_text(json.dumps({"cookies_file": 42, "profile": "best"}), encoding="utf-8")
        self.assertEqual(settings.load_settings()["cookies_file"], "")

    def test_atomic_unicode_roundtrip_only_persists_preferences(self):
        payload = {"output_dir": str(self.root / "影片"), "profile": "mp4", "url": "https://private.example/"}
        real_replace = os.replace
        with patch.object(settings.os, "replace", wraps=real_replace) as replace:
            settings.save_settings(payload)
        replace.assert_called_once()
        self.assertEqual(Path(replace.call_args.args[0]).parent, self.root)
        self.assertEqual(settings.load_settings(), {key: payload[key] for key in ("output_dir", "profile")} | {"cookies_file": ""})
        self.assertNotIn("url", json.loads((self.root / "settings.json").read_text(encoding="utf-8")))
        self.assertEqual(list(self.root.glob("settings-*.tmp")), [])

    def test_failed_replace_preserves_old_settings_and_cleans_temp(self):
        initial = {"output_dir": str(self.default), "profile": "best", "cookies_file": ""}
        settings.save_settings(initial)
        with patch.object(settings.os, "replace", side_effect=PermissionError("locked")), self.assertRaises(PermissionError):
            settings.save_settings({**initial, "profile": "mp3"})
        self.assertEqual(settings.load_settings(), initial)
        self.assertEqual(list(self.root.glob("settings-*.tmp")), [])


class ToolTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.app = self.root / "app"
        self.data = self.root / "data"
        self.addCleanup(patch.stopall)
        patch.object(tools, "data_dir", return_value=self.data).start()
        patch.object(tools, "app_dir", return_value=self.app).start()
        self.network = patch.object(tools, "urlopen", side_effect=AssertionError("Unexpected network access")).start()
        self.launch = patch.object(tools.subprocess, "run", side_effect=AssertionError("Unexpected process launch")).start()
        self.manager = tools.ToolManager()
        self.events = []
        self.version = "2026.09.01"
        self.binary = b"mock executable bytes for digest testing"

    def touch(self, path, content=b"tool"):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return str(path)

    def metadata(self):
        return {"tag_name": self.version, "assets": [{"name": "yt-dlp.exe", "size": len(self.binary),
                "browser_download_url": f"https://github.com/yt-dlp/yt-dlp/releases/download/{self.version}/yt-dlp.exe",
                "digest": "sha256:" + hashlib.sha256(self.binary).hexdigest()}]}

    def responses(self, metadata=None, binary=None):
        self.network.side_effect = [io.BytesIO(json.dumps(metadata or self.metadata()).encode()), io.BytesIO(self.binary if binary is None else binary)]
        self.launch.side_effect = None
        self.launch.return_value = subprocess.CompletedProcess([], 0, self.version + "\n", "")

    def test_discovery_prefers_updated_core_then_bundled_tools(self):
        updated = self.touch(self.data / "tools" / "yt-dlp.exe")
        self.touch(self.app / "tools" / "yt-dlp.exe")
        bundled = self.touch(self.app / "tools" / "ffmpeg.exe")
        self.touch(self.app / "ffmpeg.exe")
        adjacent = self.touch(self.app / "ffprobe.exe")
        with patch.object(tools.shutil, "which", return_value=r"C:\node\node.exe") as which:
            result = self.manager.status()
        self.assertEqual(result, {"yt_dlp": updated, "ffmpeg": bundled, "ffprobe": adjacent, "node": r"C:\node\node.exe"})
        which.assert_called_once_with("node.exe")

    def test_discovery_never_uses_path_core(self):
        with patch.object(tools.shutil, "which", return_value=None) as which:
            self.assertEqual(self.manager.status(), dict.fromkeys(TOOL_PATHS))
        self.assertNotIn(unittest.mock.call("yt-dlp.exe"), which.call_args_list)

    def test_bundled_core_fallback(self):
        adjacent = self.touch(self.app / "yt-dlp.exe")
        with patch.object(tools.shutil, "which", return_value=None):
            self.assertEqual(self.manager.status()["yt_dlp"], adjacent)
            bundled = self.touch(self.app / "tools" / "yt-dlp.exe")
            self.assertEqual(self.manager.status()["yt_dlp"], bundled)

    def test_update_pre_cancel_never_uses_network(self):
        self.manager.cancel_update()
        with self.assertRaises(models.DownloadCancelled):
            self.manager.update_core(self.events.append)
        self.network.assert_not_called()
        self.launch.assert_not_called()

    def test_update_rejects_untrusted_metadata(self):
        mutations = (("digest", ""), ("digest", "sha256:" + "z" * 64), ("digest", "sha512:" + "a" * 64),
                     ("browser_download_url", "https://evil.example/yt-dlp.exe"), ("size", 0),
                     ("size", tools.MAX_CORE_BYTES + 1), ("size", "123"))
        for key, value in mutations:
            with self.subTest(key=key, value=value):
                metadata = self.metadata()
                metadata["assets"][0][key] = value
                self.responses(metadata)
                self.network.reset_mock()
                with self.assertRaises(models.DownloadError):
                    self.manager.update_core(self.events.append)
                self.assertEqual(self.network.call_count, 1)
                self.launch.assert_not_called()

    def test_update_rejects_invalid_version(self):
        metadata = self.metadata()
        metadata["tag_name"] = "../../unsafe"
        self.responses(metadata)
        with self.assertRaises(models.DownloadError):
            self.manager.update_core(self.events.append)
        self.assertEqual(self.network.call_count, 1)

    def test_update_success_verifies_and_atomically_replaces(self):
        destination = self.data / "tools" / "yt-dlp.exe"
        self.touch(destination, b"old")
        self.responses()
        with patch.object(tools.os, "replace", wraps=os.replace) as replace:
            self.assertEqual(self.manager.update_core(self.events.append), self.version)
        replace.assert_called_once()
        self.assertEqual(destination.read_bytes(), self.binary)
        self.assertEqual(list(destination.parent.glob("yt-dlp-*.exe")), [])
        command = self.launch.call_args.args[0]
        self.assertEqual(command[1:], ["--ignore-config", "--version"])
        self.assertNotEqual(Path(command[0]), destination)
        self.assertTrue(any(event.get("percent") == 100 for event in self.events))

    def test_update_digest_size_and_startup_failures_preserve_old_core(self):
        destination = self.data / "tools" / "yt-dlp.exe"
        self.touch(destination, b"old")
        for failure in ("digest", "short", "oversize", "version", "startup"):
            with self.subTest(failure=failure):
                binary = {"digest": b"x" * len(self.binary), "short": self.binary[:-1], "oversize": self.binary + b"x"}.get(failure, self.binary)
                self.responses(binary=binary)
                if failure == "version":
                    self.launch.return_value.stdout = "wrong"
                if failure == "startup":
                    self.launch.return_value.returncode = 1
                with self.assertRaises(models.DownloadError):
                    self.manager.update_core(self.events.append)
                self.assertEqual(destination.read_bytes(), b"old")
                self.assertEqual(list(destination.parent.glob("yt-dlp-*.exe")), [])

    def test_cancel_during_download_cleans_temp_and_keeps_old_core(self):
        destination = self.data / "tools" / "yt-dlp.exe"
        self.touch(destination, b"old")
        self.responses()
        def emit(event):
            if event["type"] == "progress":
                self.manager.cancel_update()
        with self.assertRaises(models.DownloadCancelled):
            self.manager.update_core(emit)
        self.launch.assert_not_called()
        self.assertEqual(destination.read_bytes(), b"old")
        self.assertEqual(list(destination.parent.glob("yt-dlp-*.exe")), [])

    def test_cancel_after_startup_validation_prevents_replace(self):
        destination = self.data / "tools" / "yt-dlp.exe"
        self.touch(destination, b"old")
        self.responses()
        def validate(*args, **kwargs):
            self.manager.cancel_update()
            return subprocess.CompletedProcess([], 0, self.version, "")
        self.launch.side_effect = validate
        with self.assertRaises(models.DownloadCancelled):
            self.manager.update_core(self.events.append)
        self.assertEqual(destination.read_bytes(), b"old")
        self.assertEqual(list(destination.parent.glob("yt-dlp-*.exe")), [])


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.events = []
        self.manager = Mock()
        self.manager.status.return_value = TOOL_PATHS
        self.engine = engine.DownloadEngine(self.events.append, self.manager)
        self.request = models.DownloadRequest("https://example.com/video", self.root)

    def run_fake(self, metadata=None, lines=(), result=0, cancel=False):
        metadata = {"id": "123", "title": "Example"} if metadata is None else metadata
        calls = []
        def execute(args, consume):
            calls.append(args)
            if "--dump-single-json" in args:
                consume(json.dumps(metadata))
                return 0
            for line in lines:
                consume(line)
            if cancel:
                self.engine._cancel.set()
            return result
        with patch.object(self.engine, "_execute", side_effect=execute):
            self.engine.run(self.request)
        return calls

    def test_run_pre_cancel_does_not_discover_or_spawn(self):
        with patch.object(engine.threading, "Thread") as thread:
            self.engine.cancel()
        thread.return_value.start.assert_called_once()
        with patch.object(engine.subprocess, "Popen") as popen, self.assertRaises(models.DownloadCancelled):
            self.engine.run(self.request)
        popen.assert_not_called()
        self.manager.status.assert_not_called()

    def test_execute_pre_cancel_never_creates_job(self):
        self.engine._cancel.set()
        with patch.object(engine, "ProcessJob") as job, self.assertRaises(models.DownloadCancelled):
            self.engine._execute(["mock"], Mock())
        job.assert_not_called()

    def test_cancel_between_job_creation_and_launch_closes_job_without_spawn(self):
        job = Mock()
        def create_job():
            self.engine._cancel.set()
            return job
        with patch.object(engine, "ProcessJob", side_effect=create_job), patch.object(engine.subprocess, "Popen") as popen, self.assertRaises(models.DownloadCancelled):
            self.engine._execute(["mock"], Mock())
        popen.assert_not_called()
        job.close.assert_called_once()

    def test_cancel_after_process_exit_is_not_reported_as_success(self):
        process = Mock(stdout=io.StringIO())
        process.poll.return_value = 0
        def wait(*args, **kwargs):
            self.engine._cancel.set()
            return 0
        process.wait.side_effect = wait
        job = Mock()
        with patch.object(engine, "ProcessJob", return_value=job), patch.object(engine.subprocess, "Popen", return_value=process), self.assertRaises(models.DownloadCancelled):
            self.engine._execute(["mock"], Mock())
        job.close.assert_called_once()
        self.assertTrue(process.stdout.closed)

    def test_spawn_failure_still_closes_job(self):
        job = Mock()
        with patch.object(engine, "ProcessJob", return_value=job), patch.object(engine.subprocess, "Popen", side_effect=OSError("missing executable")), self.assertRaises(OSError):
            self.engine._execute(["mock"], Mock())
        job.close.assert_called_once()
        self.assertIsNone(self.engine._process)

    def test_completion_requires_marker_and_nonempty_file(self):
        output = self.root / "video.mkv"
        output.write_bytes(b"media")
        calls = self.run_fake(lines=["VD_FILE:" + json.dumps(str(output))])
        self.assertEqual([event for event in self.events if event["type"] == "completed"], [{"type": "completed", "path": str(output.resolve())}])
        self.assertEqual(len(calls), 2)
        self.assertIn("--", calls[0])
        self.assertEqual(calls[0][-1], self.request.url)
        self.assertIn("--load-info-json", calls[1])
        self.assertEqual(list(self.root.glob(".video-info-*")), [])

    def test_no_marker_does_not_claim_success(self):
        with self.assertRaises(models.DownloadError):
            self.run_fake(lines=["[download] 100%"])
        self.assertFalse(any(event["type"] == "completed" for event in self.events))

    def test_invalid_output_paths_do_not_claim_success(self):
        empty = self.root / "empty.mkv"
        empty.touch()
        with tempfile.TemporaryDirectory() as outside:
            outside_file = Path(outside) / "other.mkv"
            outside_file.write_bytes(b"media")
            for path in (empty, self.root / "missing.mkv", self.root, outside_file):
                with self.subTest(path=path), self.assertRaises(models.DownloadError):
                    self.run_fake(lines=["VD_FILE:" + json.dumps(str(path))])
        self.assertFalse(any(event["type"] == "completed" for event in self.events))

    def test_all_paths_are_validated_before_any_completed_event(self):
        valid = self.root / "valid.mkv"
        valid.write_bytes(b"media")
        with self.assertRaises(models.DownloadError):
            self.run_fake(lines=["VD_FILE:" + json.dumps(str(path)) for path in (valid, self.root / "missing.mkv")])
        self.assertFalse(any(event["type"] == "completed" for event in self.events))

    def test_failed_exit_or_cancellation_overrides_completion_marker(self):
        output = self.root / "video.mkv"
        output.write_bytes(b"media")
        lines = ["VD_FILE:" + json.dumps(str(output))]
        with self.assertRaises(models.DownloadError):
            self.run_fake(lines=lines, result=1)
        with self.assertRaises(models.DownloadCancelled):
            self.run_fake(lines=lines, cancel=True)
        self.assertFalse(any(event["type"] == "completed" for event in self.events))

    def test_playlist_and_live_metadata_are_rejected(self):
        for metadata in ({"_type": "playlist"}, {"entries": []}, {"_type": "multi_video"}, {"is_live": True},
                         {"live_status": "is_upcoming"}, {"live_status": "post_live"}, {}):
            with self.subTest(metadata=metadata), self.assertRaises(models.DownloadError):
                self.run_fake(metadata=metadata)
        self.assertEqual(list(self.root.glob(".video-info-*")), [])

    def test_execute_assigns_before_resume_and_closes_resources(self):
        process = Mock(stdout=io.StringIO("one\nsecond\r\n"))
        process.poll.return_value = 0
        process.wait.return_value = 0
        job = Mock()
        order = Mock()
        order.attach_mock(job, "job")
        order.attach_mock(process, "process")
        consume = Mock()
        with patch.object(engine, "ProcessJob", return_value=job), patch.object(engine.subprocess, "Popen", return_value=process) as popen:
            self.assertEqual(self.engine._execute(["mock"], consume), 0)
        self.assertLess(order.mock_calls.index(unittest.mock.call.job.assign(process)), order.mock_calls.index(unittest.mock.call.job.resume(process)))
        if os.name == "nt":
            self.assertTrue(popen.call_args.kwargs["creationflags"] & 4)
        self.assertFalse(popen.call_args.kwargs.get("shell", False))
        self.assertEqual(consume.call_args_list, [unittest.mock.call("one"), unittest.mock.call("second")])
        job.close.assert_called_once()
        self.assertTrue(process.stdout.closed)
        self.assertIsNone(self.engine._process)
        self.assertIsNone(self.engine._job)

    def test_cancel_during_execute_terminates_job_and_cleans_up(self):
        process = Mock(stdout=io.StringIO("first\nsecond\n"))
        process.poll.return_value = None
        job = Mock()
        def consume(line):
            self.engine._cancel.set()
        with patch.object(engine, "ProcessJob", return_value=job), patch.object(engine.subprocess, "Popen", return_value=process), self.assertRaises(models.DownloadCancelled):
            self.engine._execute(["mock"], consume)
        job.terminate.assert_called_once_with(process)
        job.close.assert_called_once()
        self.assertTrue(process.stdout.closed)
        self.assertIsNone(self.engine._process)

    def test_termination_failure_still_closes_job_and_stream(self):
        process = Mock(stdout=io.StringIO("line\n"))
        process.poll.return_value = None
        job = Mock()
        job.terminate.side_effect = OSError("job termination failed")
        def consume(line):
            raise models.DownloadCancelled("cancelled")
        with patch.object(engine, "ProcessJob", return_value=job), patch.object(engine.subprocess, "Popen", return_value=process), self.assertRaises(models.DownloadCancelled):
            self.engine._execute(["mock"], consume)
        process.kill.assert_called()
        job.close.assert_called_once()
        self.assertTrue(process.stdout.closed)
        self.assertIsNone(self.engine._process)
        self.assertIsNone(self.engine._job)

    def test_assignment_failure_kills_suspended_process(self):
        process = Mock(stdout=io.StringIO())
        process.poll.return_value = None
        job = Mock()
        job.assign.side_effect = OSError("assignment failed")
        with patch.object(engine, "ProcessJob", return_value=job), patch.object(engine.subprocess, "Popen", return_value=process), self.assertRaises(OSError):
            self.engine._execute(["mock"], Mock())
        job.resume.assert_not_called()
        process.kill.assert_called()
        job.close.assert_called_once()
        self.assertTrue(process.stdout.closed)

    def test_terminate_falls_back_to_process_kill(self):
        process = Mock()
        process.poll.return_value = None
        job = Mock()
        job.terminate.side_effect = OSError("failed")
        self.engine._process, self.engine._job = process, job
        self.engine._terminate()
        process.kill.assert_called_once()


@unittest.skipUnless(os.name == "nt", "Windows Job Object ABI")
class WindowsJobTests(unittest.TestCase):
    def test_job_initialization_sets_kill_on_close_and_preserves_handle_width(self):
        kernel = Mock()
        handle = 0x1234567887654321
        kernel.CreateJobObjectW.return_value = handle
        kernel.SetInformationJobObject.return_value = 1
        captured = []
        def set_info(actual_handle, info_class, pointer, size):
            captured.append((actual_handle, info_class, pointer._obj.BasicLimitInformation.LimitFlags, size))
            return 1
        kernel.SetInformationJobObject.side_effect = set_info
        with patch.object(processes.ctypes, "WinDLL", return_value=kernel):
            job = processes.ProcessJob()
        self.assertEqual(job.handle, handle)
        self.assertEqual(captured[0][:3], (handle, 9, 0x2000))
        self.assertEqual(kernel.CreateJobObjectW.restype, processes.wintypes.HANDLE)
        self.assertEqual(kernel.AssignProcessToJobObject.argtypes, [processes.wintypes.HANDLE, processes.wintypes.HANDLE])
        job.close()
        job.close()
        kernel.CloseHandle.assert_called_once_with(handle)

    def test_windows_structure_sizes_match_abi(self):
        pointer_size = processes.ctypes.sizeof(processes.ctypes.c_void_p)
        self.assertEqual(processes.ctypes.sizeof(processes._IOCounters), 48)
        self.assertEqual(processes.ctypes.sizeof(processes._BasicLimits), 64 if pointer_size == 8 else 48)
        self.assertEqual(processes.ctypes.sizeof(processes._ExtendedLimits), 144 if pointer_size == 8 else 112)

    def test_job_assignment_and_resume_use_process_handle(self):
        kernel = Mock()
        kernel.CreateJobObjectW.return_value = 123
        kernel.SetInformationJobObject.return_value = 1
        kernel.AssignProcessToJobObject.return_value = 1
        ntdll = Mock()
        ntdll.NtResumeProcess.return_value = 0
        process = Mock(_handle=456)
        with patch.object(processes.ctypes, "WinDLL", side_effect=[kernel, ntdll]):
            job = processes.ProcessJob()
            job.assign(process)
            job.resume(process)
            job.close()
        kernel.AssignProcessToJobObject.assert_called_once_with(123, 456)
        ntdll.NtResumeProcess.assert_called_once_with(456)


if __name__ == "__main__":
    unittest.main()