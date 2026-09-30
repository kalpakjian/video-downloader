"""Downloader CLI adapter: typed events, cancellable child jobs, no shell."""

from collections import deque
import json
import math
import os
from pathlib import Path
import subprocess
import tempfile
import threading
from urllib.parse import urlsplit

from .models import DownloadCancelled, DownloadError, DownloadRequest, PROFILE_BY_ID, validate_url
from .processes import ProcessJob
from .tools import ToolManager, hidden_process_options

PROGRESS_PREFIX = "VD_PROGRESS:"
POST_PREFIX = "VD_POST:"
FILE_PREFIX = "VD_FILE:"


def _number(value):
    if isinstance(value, bool):
        return None
    try:
        value = float(value)
        return value if math.isfinite(value) and value >= 0 else None
    except (TypeError, ValueError, OverflowError):
        return None


def format_speed(value) -> str:
    value = _number(value)
    if value is None:
        return ""
    for unit in ("B/s", "KiB/s", "MiB/s", "GiB/s"):
        if value < 1024 or unit == "GiB/s":
            return f"{value:.1f} {unit}"
        value /= 1024
    return ""


def parse_event(line: str) -> dict | None:
    """Only explicit machine-readable markers drive progress/completion."""
    line = line.strip()
    if line.startswith(FILE_PREFIX):
        try:
            path = json.loads(line[len(FILE_PREFIX):])
            if isinstance(path, str) and path:
                return {"type": "completed", "path": path}
        except (ValueError, TypeError):
            pass
        return None
    phase = "processing" if line.startswith(POST_PREFIX) else "download"
    prefix = POST_PREFIX if phase == "processing" else PROGRESS_PREFIX
    if not line.startswith(prefix):
        return None
    try:
        progress = json.loads(line[len(prefix):])
        if not isinstance(progress, dict):
            return None
    except (ValueError, TypeError):
        return None
    done = _number(progress.get("downloaded_bytes"))
    total = _number(progress.get("total_bytes")) or _number(progress.get("total_bytes_estimate"))
    percent = min(100.0, done * 100 / total) if done is not None and total else None
    eta = _number(progress.get("eta"))
    eta_text = "" if eta is None else f"{int(eta) // 60:02d}:{int(eta) % 60:02d}"
    if phase == "processing":
        percent = None
    return {"type": "progress", "percent": percent, "speed": format_speed(progress.get("speed")),
            "eta": eta_text, "phase": phase}


def friendly_error(text: str, profile: str = "best", cookies: bool = False) -> str:
    value = text.lower()
    if any(word in value for word in ("no video could be found in this tweet", "tweettombstone",
                                     "tombstone", "sensitive-media", "age-restricted")):
        base = "此 X（Twitter）貼文對未登入訪客隱藏，多為敏感或年齡限制內容，X 僅開放給已登入使用者觀看。"
        if cookies:
            return base + "已使用指定的 cookies.txt 仍無法取得，cookie 可能已過期或失效，請重新匯出後再試。"
        return base + "如需下載此類內容，請在主畫面第 4 步指定你自行匯出的 cookies.txt；本工具不會自動讀取帳號或 Cookie。"
    if any(word in value for word in ("sign in", "login", "log in", "cookies", "private video", "authentication")):
        return "平台要求登入或驗證，或影片不是公開內容。本工具不會自動讀取帳號或 Cookie；請改用可公開取得的影片。"
    if "drm" in value:
        return "此內容受 DRM 保護，本工具不支援解除保護。"
    if any(word in value for word in ("geo", "not available in your country", "not available in your region")):
        return "此影片有地區限制，目前的網路位置無法取得。"
    if "requested format" in value or "no video formats" in value:
        if profile == "mp4":
            return "找不到相容的 H.264／AAC 來源。請改選「最高畫質」；本工具不會偷偷降低設定或重新壓縮。"
        return "找不到符合所選畫質的來源。請嘗試「最高畫質」、更新下載核心，或確認影片仍可公開播放。"
    if "unsupported url" in value:
        return "此網址目前不受下載核心支援。請使用單支影片的分享網址，或更新下載核心後重試。"
    if "429" in value or "too many requests" in value:
        return "平台暫時限制請求頻率。請稍後再試，避免連續重試。"
    if "403" in value or "forbidden" in value:
        return "平台拒絕存取（403）。公開影片也可能需要登入或受到反機器人限制；可更新核心後重試。"
    if any(word in value for word in ("timed out", "timeout", "resolve", "connection", "certificate")):
        return "網路連線、DNS 或憑證驗證失敗。請確認網路與系統時間，再試一次；本工具不會停用 HTTPS 驗證。"
    if "no space" in value or "disk full" in value:
        return "磁碟空間不足，請清理空間或更換儲存位置。"
    if any(word in value for word in ("permission", "access is denied", "unable to open")):
        return "無法寫入檔案。請選擇可寫入的資料夾，並確認檔案未被其他程式占用。"
    if any(word in value for word in ("removed", "unavailable", "not found", "404")):
        return "影片可能已移除、失效或不可公開取得。請確認網址可在瀏覽器播放。"
    return "下載失敗。請查看下方核心訊息，確認網址可公開播放，或更新核心後重試。"


def build_common_args(request: DownloadRequest, tools: dict) -> list[str]:
    url = validate_url(request.url)
    if request.profile not in PROFILE_BY_ID:
        raise DownloadError("不支援的下載格式，請重新選擇。")
    if not tools.get("yt_dlp"):
        raise DownloadError("尚未安裝下載核心，請先按「更新下載核心」。")
    if not tools.get("ffmpeg") or not tools.get("ffprobe"):
        raise DownloadError("找不到 FFmpeg／FFprobe。請安裝兩者並加入 PATH，或放進程式旁的 tools 資料夾後重開程式。")
    host = urlsplit(url).hostname.lower()
    if not tools.get("node") and any(host == domain or host.endswith("." + domain)
                                     for domain in ("youtube.com", "youtu.be")):
        raise DownloadError("YouTube 需要 Node.js 22 以上版本。請安裝後重新開啟程式。")
    profile = PROFILE_BY_ID[request.profile]
    args = [tools["yt_dlp"], "--ignore-config", "--no-plugin-dirs", "--no-cache-dir", "--no-playlist",
            "--socket-timeout", "20", "--retries", "3", "--fragment-retries", "3",
            "--extractor-retries", "2", "--abort-on-unavailable-fragments",
            "--encoding", "utf-8", "--color", "never", "--no-update",
            "--ffmpeg-location", str(Path(tools["ffmpeg"]).parent), "--format", profile.selector]
    cookies = (getattr(request, "cookies", "") or "").strip()
    if cookies:
        if "\x00" in cookies:
            raise DownloadError("cookies 檔案路徑無效，請重新選擇或清空該欄位。")
        cookie_path = Path(cookies).expanduser()
        if not cookie_path.is_absolute() or not cookie_path.is_file():
            raise DownloadError("找不到指定的 cookies.txt 檔案。請重新匯出，或清空欄位改用匿名下載。")
        args.extend(("--cookies", str(cookie_path)))
    if tools.get("node"):
        args.extend(("--js-runtimes", f"node:{tools['node']}"))
    return args


class DownloadEngine:
    def __init__(self, emit, tools: ToolManager | None = None):
        self.emit = emit
        self.tools = tools or ToolManager()
        self._cancel = threading.Event()
        self._lock = threading.Lock()
        self._process = None
        self._job = None

    def _check_cancel(self):
        if self._cancel.is_set():
            raise DownloadCancelled("已取消下載；未完成的 .part 檔案保留，可用相同網址與格式重試續傳。")

    def cancel(self) -> None:
        self._cancel.set()
        threading.Thread(target=self._terminate, daemon=True).start()

    def _terminate(self):
        with self._lock:
            if self._process is not None and self._job is not None:
                try:
                    self._job.terminate(self._process)
                except OSError:
                    if self._process.poll() is None:
                        self._process.kill()

    def _execute(self, args, consume) -> int:
        self._check_cancel()
        process = None
        job = ProcessJob()
        try:
            options = hidden_process_options()
            if os.name == "nt":
                options["creationflags"] |= 0x00000004  # CREATE_SUSPENDED
            with self._lock:
                self._check_cancel()
                process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                           stdin=subprocess.DEVNULL, text=True, encoding="utf-8",
                                           errors="replace", bufsize=1, **options)
                job.assign(process)
                self._process, self._job = process, job
                job.resume(process)
            for line in process.stdout:
                self._check_cancel()
                consume(line.rstrip("\r\n"))
            result = process.wait()
            self._check_cancel()
            return result
        finally:
            try:
                with self._lock:
                    try:
                        if process is not None and process.poll() is None:
                            try:
                                job.terminate(process)
                            except OSError:
                                pass
                            finally:
                                # Assignment may have failed, leaving an empty
                                # job and an unassigned suspended process.
                                if process.poll() is None:
                                    process.kill()
                    finally:
                        job.close()
                        self._process, self._job = None, None
                if process is not None:
                    process.wait(timeout=10)
            finally:
                if process is not None and process.stdout:
                    process.stdout.close()

    def run(self, request: DownloadRequest) -> None:
        self._check_cancel()
        common = build_common_args(request, self.tools.status())
        folder = Path(request.output_dir).expanduser()
        if not folder.is_absolute():
            raise DownloadError("儲存位置必須是完整的絕對路徑。")
        try:
            folder.mkdir(parents=True, exist_ok=True)
            folder = folder.resolve()
            with tempfile.TemporaryDirectory(prefix=".video-info-", dir=folder) as temporary:
                self._run_in_folder(request, common, folder, Path(temporary))
        except DownloadError:
            raise
        except OSError as exc:
            raise DownloadError(f"無法啟動工具或存取檔案：{exc}\n請確認儲存位置可寫入、磁碟空間足夠，且工具未被防毒隔離。") from exc

    def _run_in_folder(self, request, common, folder, temporary):
        self.emit({"type": "status", "message": "正在解析影片與可用畫質…"})
        metadata = None
        errors = deque(maxlen=12)

        def metadata_line(line):
            nonlocal metadata
            if line.startswith("{"):
                if len(line) > 16 * 1024 * 1024:
                    raise DownloadError("影片資訊過大，已中止處理。")
                try:
                    parsed = json.loads(line)
                    if isinstance(parsed, dict):
                        metadata = parsed
                        return
                except ValueError:
                    pass
            if line:
                errors.append(line)
                self.emit({"type": "log", "message": line[:2000]})

        result = self._execute(common + ["--dump-single-json", "--skip-download", "--flat-playlist",
                                         "--playlist-end", "1", "--", validate_url(request.url)], metadata_line)
        if result:
            raise DownloadError(friendly_error("\n".join(errors), request.profile, bool(getattr(request, "cookies", ""))))
        if not metadata:
            raise DownloadError("下載核心未回傳影片資訊；請更新核心或換一個影片網址。")
        if metadata.get("_type") in {"playlist", "multi_video"} or "entries" in metadata:
            raise DownloadError("第一版只下載單支影片，不下載播放清單、頻道或多影片貼文。請貼上單支影片網址。")
        if metadata.get("is_live") or metadata.get("live_status") in {"is_live", "is_upcoming", "post_live"}:
            raise DownloadError("第一版不錄製直播或尚未完成處理的直播。請等待直播結束並轉為可下載影片。")
        info = temporary / "source.info.json"
        info.write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf-8")
        self._check_cancel()
        title = str(metadata.get("title") or metadata.get("id") or "影片")
        self.emit({"type": "log", "message": f"影片：{title[:300]}"})
        self.emit({"type": "status", "message": "正在下載…影像與音訊可能分段下載，百分比會依各段重新計算。"})
        profile = PROFILE_BY_ID[request.profile]
        args = common + ["--load-info-json", str(info), "--no-simulate", "--newline", "--progress",
                         "--no-quiet", "--progress-delta", "0.3", "--windows-filenames", "--trim-filenames", "160",
                         "--no-overwrites", "--continue", "--paths", str(folder),
                         "--output", f"%(title).100s [%(id).40s] [{profile.id}].%(ext)s",
                         "--progress-template", f"download:{PROGRESS_PREFIX}%(progress)j",
                         "--progress-template", f"postprocess:{POST_PREFIX}%(progress)j",
                         "--print", f"after_move:{FILE_PREFIX}%(filepath)j", *profile.extra_args]
        final_paths = []

        def download_line(line):
            event = parse_event(line)
            if event:
                if event["type"] == "completed":
                    final_paths.append(Path(event["path"]))
                else:
                    self.emit(event)
                return
            if line:
                errors.append(line)
                self.emit({"type": "log", "message": line[:2000]})
                if line.startswith(("[Merger]", "[ExtractAudio]", "[VideoRemuxer]", "[Fixup")):
                    self.emit({"type": "status", "message": "下載資料已取得，正在合併或處理媒體…"})
                    self.emit({"type": "progress", "percent": None, "speed": "", "eta": "", "phase": "processing"})

        errors.clear()
        result = self._execute(args, download_line)
        self._check_cancel()
        if result:
            raise DownloadError(friendly_error("\n".join(errors), request.profile, bool(getattr(request, "cookies", ""))))
        if not final_paths:
            raise DownloadError("核心已結束，但沒有確認最終輸出檔案，未標記為下載成功。")
        verified_paths = []
        for path in final_paths:
            path = path.resolve()
            if not path.is_relative_to(folder) or not path.is_file() or path.stat().st_size == 0:
                raise DownloadError("最終輸出檔案不存在、是空檔或不在所選資料夾中，未標記為下載成功。")
            verified_paths.append(path)
        for path in verified_paths:
            self.emit({"type": "completed", "path": str(path)})
