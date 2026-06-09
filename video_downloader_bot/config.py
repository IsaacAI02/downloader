from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path


class ConfigError(ValueError):
    """Raised when required configuration is missing or invalid."""


def _csv(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(item.strip().lower().lstrip(".") for item in value.split(",") if item.strip())


def _int_env(name: str, default: int, *, minimum: int = 1) -> int:
    raw = os.getenv(name, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer.") from exc
    if value < minimum:
        raise ConfigError(f"{name} must be at least {minimum}.")
    return value


def _bool_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def _webhook_path(value: str | None) -> str:
    path = (value or "telegram-webhook").strip().strip("/")
    if not path:
        raise ConfigError("WEBHOOK_PATH cannot be empty.")
    if not re.fullmatch(r"[A-Za-z0-9._~/-]+", path):
        raise ConfigError("WEBHOOK_PATH contains unsupported characters.")
    return path


def _owner_ids(value: str | None) -> tuple[int, ...]:
    if not value:
        return ()

    ids: list[int] = []
    for item in value.split(","):
        item = item.strip()
        if not item:
            continue
        try:
            ids.append(int(item))
        except ValueError as exc:
            raise ConfigError("BOT_OWNER_IDS must contain only Telegram numeric IDs.") from exc
    return tuple(ids)


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    max_upload_mb: int
    max_concurrent_downloads: int
    download_timeout_seconds: int
    network_timeout_seconds: int
    download_dir: Path
    bot_owner_ids: tuple[int, ...]
    allowed_domains: tuple[str, ...]
    blocked_domains: tuple[str, ...]
    allow_private_urls: bool
    ytdlp_cookies_file: Path | None
    ytdlp_user_agent: str | None
    ytdlp_format: str | None
    ytdlp_audio_format: str | None
    audio_bitrate_kbps: int
    voice_bitrate_kbps: int
    ffmpeg_location: str | None
    webhook_url: str | None
    webhook_path: str
    webhook_secret_token: str | None
    port: int
    telegram_api_base_url: str | None
    telegram_api_base_file_url: str | None

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @classmethod
    def from_env(cls) -> "Settings":
        token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        if not token or token == "123456:replace-me":
            raise ConfigError("Set TELEGRAM_BOT_TOKEN in your environment or .env file.")

        cookies = os.getenv("YTDLP_COOKIES_FILE", "").strip()

        return cls(
            telegram_bot_token=token,
            max_upload_mb=_int_env("MAX_UPLOAD_MB", 45),
            max_concurrent_downloads=_int_env("MAX_CONCURRENT_DOWNLOADS", 1),
            download_timeout_seconds=_int_env("DOWNLOAD_TIMEOUT_SECONDS", 600),
            network_timeout_seconds=_int_env("NETWORK_TIMEOUT_SECONDS", 30),
            download_dir=Path(os.getenv("DOWNLOAD_DIR", "downloads")).expanduser(),
            bot_owner_ids=_owner_ids(os.getenv("BOT_OWNER_IDS")),
            allowed_domains=_csv(os.getenv("ALLOWED_DOMAINS")),
            blocked_domains=_csv(os.getenv("BLOCKED_DOMAINS")),
            allow_private_urls=_bool_env("ALLOW_PRIVATE_URLS", False),
            ytdlp_cookies_file=Path(cookies).expanduser() if cookies else None,
            ytdlp_user_agent=os.getenv("YTDLP_USER_AGENT", "").strip() or None,
            ytdlp_format=os.getenv("YTDLP_FORMAT", "").strip() or None,
            ytdlp_audio_format=os.getenv("YTDLP_AUDIO_FORMAT", "").strip() or None,
            audio_bitrate_kbps=_int_env("AUDIO_BITRATE_KBPS", 128),
            voice_bitrate_kbps=_int_env("VOICE_BITRATE_KBPS", 48),
            ffmpeg_location=os.getenv("FFMPEG_LOCATION", "").strip() or None,
            webhook_url=os.getenv("WEBHOOK_URL", "").strip().rstrip("/") or None,
            webhook_path=_webhook_path(os.getenv("WEBHOOK_PATH")),
            webhook_secret_token=os.getenv("WEBHOOK_SECRET_TOKEN", "").strip() or None,
            port=_int_env("PORT", 10000),
            telegram_api_base_url=os.getenv("TELEGRAM_API_BASE_URL", "").strip() or None,
            telegram_api_base_file_url=os.getenv("TELEGRAM_API_BASE_FILE_URL", "").strip() or None,
        )
