from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError as YtDlpDownloadError

from .config import Settings


logger = logging.getLogger(__name__)
MediaKind = Literal["video", "audio", "voice"]


class DownloadError(RuntimeError):
    """Raised when yt-dlp cannot download a URL."""


class DownloadTooLarge(DownloadError):
    def __init__(self, file_size: int, max_size: int) -> None:
        self.file_size = file_size
        self.max_size = max_size
        super().__init__(f"Downloaded file is {file_size} bytes, above the {max_size} byte limit.")


@dataclass(frozen=True)
class DownloadResult:
    file_path: Path
    directory: Path
    title: str
    source_url: str
    duration: int | None
    media_kind: MediaKind

    @property
    def file_size(self) -> int:
        return self.file_path.stat().st_size

    def cleanup(self) -> None:
        shutil.rmtree(self.directory, ignore_errors=True)


class YtDlpLogger:
    def debug(self, message: str) -> None:
        logger.debug(message)

    def warning(self, message: str) -> None:
        logger.warning(message)

    def error(self, message: str) -> None:
        logger.error(message)


class VideoDownloader:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def download(self, url: str, media_kind: MediaKind = "video") -> DownloadResult:
        self.settings.download_dir.mkdir(parents=True, exist_ok=True)
        job_dir = Path(tempfile.mkdtemp(prefix="job-", dir=self.settings.download_dir))

        try:
            info = self._download_with_ytdlp(url, job_dir, media_kind)
            file_path = self._find_downloaded_file(info, job_dir)

            if media_kind == "audio":
                file_path = self._convert_to_mp3(file_path)
            elif media_kind == "voice":
                file_path = self._convert_to_voice(file_path)

            size = file_path.stat().st_size

            if size > self.settings.max_upload_bytes:
                raise DownloadTooLarge(size, self.settings.max_upload_bytes)

            return DownloadResult(
                file_path=file_path,
                directory=job_dir,
                title=str(info.get("title") or file_path.stem),
                source_url=str(info.get("webpage_url") or url),
                duration=info.get("duration") if isinstance(info.get("duration"), int) else None,
                media_kind=media_kind,
            )
        except Exception:
            shutil.rmtree(job_dir, ignore_errors=True)
            raise

    def _download_with_ytdlp(self, url: str, job_dir: Path, media_kind: MediaKind) -> dict[str, Any]:
        options = self._yt_dlp_options(job_dir, media_kind)

        try:
            with YoutubeDL(options) as ydl:
                info = ydl.extract_info(url, download=True)
        except YtDlpDownloadError as exc:
            raise DownloadError(str(exc)) from exc

        if not isinstance(info, dict):
            raise DownloadError("The downloader did not return video information.")

        if "entries" in info:
            entries = [entry for entry in info.get("entries") or [] if entry]
            if not entries:
                raise DownloadError("No downloadable videos were found in that link.")
            info = entries[0]

        return info

    def _yt_dlp_options(self, job_dir: Path, media_kind: MediaKind) -> dict[str, Any]:
        options: dict[str, Any] = {
            "format": self._format_for(media_kind),
            "outtmpl": str(job_dir / "%(title).180B [%(id)s].%(ext)s"),
            "paths": {"home": str(job_dir), "temp": str(job_dir)},
            "noplaylist": True,
            "max_filesize": self.settings.max_upload_bytes,
            "retries": 3,
            "fragment_retries": 3,
            "socket_timeout": self.settings.network_timeout_seconds,
            "continuedl": False,
            "overwrites": True,
            "windowsfilenames": True,
            "quiet": True,
            "no_warnings": True,
            "logger": YtDlpLogger(),
        }

        ffmpeg_path = self._ffmpeg_path(required=False)
        if ffmpeg_path:
            options["ffmpeg_location"] = ffmpeg_path
        if ffmpeg_path and media_kind == "video":
            options["merge_output_format"] = "mp4"

        if self.settings.ytdlp_cookies_file:
            options["cookiefile"] = str(self.settings.ytdlp_cookies_file)

        if self.settings.ytdlp_user_agent:
            options["http_headers"] = {"User-Agent": self.settings.ytdlp_user_agent}

        return options

    def _format_for(self, media_kind: MediaKind) -> str:
        if media_kind == "video":
            return self.settings.ytdlp_format or self._default_video_format()
        return self.settings.ytdlp_audio_format or "bestaudio/best"

    def _default_video_format(self) -> str:
        max_bytes = self.settings.max_upload_bytes
        return (
            f"best[filesize<={max_bytes}][ext=mp4]/"
            f"best[filesize<={max_bytes}]/"
            "best[ext=mp4]/best"
        )

    def _convert_to_mp3(self, input_path: Path) -> Path:
        if input_path.suffix.lower() == ".mp3":
            return input_path

        output_path = input_path.with_suffix(".mp3")
        self._run_ffmpeg(
            [
                "-y",
                "-i",
                str(input_path),
                "-vn",
                "-codec:a",
                "libmp3lame",
                "-b:a",
                f"{self.settings.audio_bitrate_kbps}k",
                str(output_path),
            ]
        )
        return output_path

    def _convert_to_voice(self, input_path: Path) -> Path:
        output_path = input_path.with_suffix(".voice.ogg")
        self._run_ffmpeg(
            [
                "-y",
                "-i",
                str(input_path),
                "-vn",
                "-ac",
                "1",
                "-ar",
                "48000",
                "-c:a",
                "libopus",
                "-b:a",
                f"{self.settings.voice_bitrate_kbps}k",
                "-vbr",
                "on",
                "-application",
                "voip",
                str(output_path),
            ]
        )
        return output_path

    def _run_ffmpeg(self, arguments: list[str]) -> None:
        ffmpeg_path = self._ffmpeg_path(required=True)
        assert ffmpeg_path is not None

        completed = subprocess.run(
            [ffmpeg_path, *arguments],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=self.settings.download_timeout_seconds,
            check=False,
        )
        if completed.returncode != 0:
            detail = completed.stderr.strip().splitlines()[-1:] or ["unknown ffmpeg error"]
            raise DownloadError(f"ffmpeg conversion failed: {detail[0]}")

    def _ffmpeg_path(self, *, required: bool) -> str | None:
        if self.settings.ffmpeg_location:
            return self.settings.ffmpeg_location

        found = shutil.which("ffmpeg")
        if found:
            return found

        try:
            from imageio_ffmpeg import get_ffmpeg_exe
        except ImportError:
            bundled = None
        else:
            bundled = get_ffmpeg_exe()

        if bundled:
            return bundled

        if required:
            raise DownloadError("ffmpeg is required for audio and voice conversion.")

        return None

    def _find_downloaded_file(self, info: dict[str, Any], job_dir: Path) -> Path:
        requested_downloads = info.get("requested_downloads")
        if isinstance(requested_downloads, list):
            for requested in requested_downloads:
                if not isinstance(requested, dict):
                    continue
                candidate = requested.get("filepath") or requested.get("_filename")
                if candidate and Path(candidate).is_file():
                    return Path(candidate)

        candidate = info.get("filepath") or info.get("_filename")
        if candidate and Path(candidate).is_file():
            return Path(candidate)

        files = [
            path
            for path in job_dir.iterdir()
            if path.is_file() and not path.name.endswith((".part", ".ytdl", ".tmp"))
        ]

        if not files:
            raise DownloadError("The download finished, but no media file was found.")

        return max(files, key=lambda path: path.stat().st_mtime)
