"""Validated requests and explicit, non-upscaling format policies."""

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit
import re


class DownloadError(Exception):
    """An actionable error safe to display in the interface."""


class DownloadCancelled(DownloadError):
    """The user intentionally cancelled the current operation."""


@dataclass(frozen=True)
class Profile:
    id: str
    label: str
    description: str
    selector: str
    extra_args: tuple[str, ...]


PROFILES = (
    Profile("best", "最高畫質・保留原始編碼", "選擇可取得的最佳音畫，不重新壓縮；合併為 MKV，單檔保留來源格式。",
            "bv+ba/b", ("--merge-output-format", "mkv")),
    Profile("mp4", "MP4 影片・相容模式", "僅選 H.264／AAC 來源，可能低於最高畫質；無相容來源時提示，不偷偷轉檔。",
            "bv[vcodec~='^(avc1|h264)']+ba[acodec~='^(mp4a|aac)']/b[vcodec~='^(avc1|h264)'][acodec~='^(mp4a|aac)']",
            ("--merge-output-format", "mp4", "--remux-video", "mp4")),
    Profile("1080p", "影片・1080p 以下", "選擇高度不超過 1080p 的最佳來源；不放大、不重新壓縮，必要時使用 MKV。",
            "bv[height<=1080]+ba/b[height<=1080]", ("--merge-output-format", "mkv")),
    Profile("720p", "影片・720p 以下", "選擇高度不超過 720p 的最佳來源；不放大、不重新壓縮，必要時使用 MKV。",
            "bv[height<=720]+ba/b[height<=720]", ("--merge-output-format", "mkv")),
    Profile("mp3", "MP3 音訊", "擷取最佳可用音源並有損轉成 MP3（V0）；不會提升原始音質。",
            "ba/b", ("--extract-audio", "--audio-format", "mp3", "--audio-quality", "0")),
)
PROFILE_BY_ID = {profile.id: profile for profile in PROFILES}


@dataclass(frozen=True)
class DownloadRequest:
    url: str
    output_dir: Path
    profile: str = "best"


def validate_url(value: str) -> str:
    value = value.strip()
    if not value:
        raise DownloadError("請先貼上影片網址。")
    if len(value) > 8192 or re.search(r"[\s\x00-\x1f\x7f]", value):
        raise DownloadError("請一次輸入一個完整網址，不要包含空白或換行。")
    try:
        parsed = urlsplit(value)
        host = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise DownloadError("網址格式不正確，請重新複製完整的影片網址。") from exc
    if parsed.scheme.lower() not in {"http", "https"} or not host:
        raise DownloadError("僅接受 http:// 或 https:// 的影片網址，不接受檔案或指令。")
    if parsed.username is not None or parsed.password is not None:
        raise DownloadError("請勿在網址中包含帳號或密碼。")
    if "\\" in value or port == 0:
        raise DownloadError("網址格式不正確。")
    return value