from __future__ import annotations

import asyncio
import contextlib
import logging
from pathlib import Path

from dotenv import load_dotenv
from telegram import Update
from telegram.constants import ChatAction
from telegram.error import TelegramError
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from .config import ConfigError, Settings
from .downloader import DownloadError, DownloadResult, DownloadTooLarge, MediaKind, VideoDownloader
from .url_tools import extract_urls, validate_url


logging.basicConfig(
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


START_TEXT = """Send me a public video link and I will try to download it.

Only use this bot for videos you own, have permission to download, or are legally allowed to save. I do not bypass DRM.

Commands:
/audio <url> - send audio
/voice <url> - send a voice message
/help - show usage and limits
/status - show bot configuration"""


class TelegramVideoBot:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.downloader = VideoDownloader(settings)
        self.semaphore = asyncio.Semaphore(settings.max_concurrent_downloads)

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        del context
        if update.message:
            await update.message.reply_text(START_TEXT)

    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        del context
        if not update.message:
            return

        await update.message.reply_text(
            "Paste one video URL per message, or use /audio <url> and /voice <url>. "
            "The bot uses yt-dlp, so many public video platforms work.\n\n"
            f"Current upload limit: {self.settings.max_upload_mb} MB.\n"
            "Playlists are disabled; send a direct video/post URL.\n"
            "Audio sends an MP3 file. Voice sends an OGG/Opus Telegram voice note.\n"
            "Some sites need cookies or may block automated downloads. Add YTDLP_COOKIES_FILE in .env for "
            "accounts/content you are authorized to access."
        )

    async def status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        del context
        if not update.message:
            return

        domains = ", ".join(self.settings.allowed_domains) if self.settings.allowed_domains else "any public domain"
        restricted = "yes" if self.settings.bot_owner_ids else "no"

        await update.message.reply_text(
            f"Max upload: {self.settings.max_upload_mb} MB\n"
            f"Concurrent downloads: {self.settings.max_concurrent_downloads}\n"
            f"Allowed domains: {domains}\n"
            f"Owner restricted: {restricted}"
        )

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._handle_url_request(update, context, "video")

    async def audio(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._handle_url_request(update, context, "audio")

    async def voice(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._handle_url_request(update, context, "voice")

    async def _handle_url_request(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        media_kind: MediaKind,
    ) -> None:
        if not update.message or not update.message.text:
            return

        if not self._is_authorized(update):
            await update.message.reply_text("This bot is private.")
            return

        urls = extract_urls(update.message.text)
        if not urls:
            await update.message.reply_text("Send me a video URL that starts with http:// or https://.")
            return

        url = urls[0]
        validation = validate_url(url, self.settings)
        if not validation.ok:
            await update.message.reply_text(validation.error or "That URL is not allowed.")
            return

        if len(urls) > 1:
            await update.message.reply_text("I found multiple URLs. I will process the first one.")

        queued = self.semaphore.locked()
        status_message = await update.message.reply_text("Queued..." if queued else "Checking the link...")

        async with self.semaphore:
            await self._process_download(update, context, url, status_message.message_id, media_kind)

    async def _process_download(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        url: str,
        status_message_id: int,
        media_kind: MediaKind,
    ) -> None:
        assert update.message is not None
        chat_id = update.effective_chat.id if update.effective_chat else update.message.chat_id

        label = self._media_label(media_kind)
        await self._edit_status(context, chat_id, status_message_id, f"Downloading {label}...")
        action_task = asyncio.create_task(self._chat_action_loop(context, chat_id, self._chat_action(media_kind)))
        result: DownloadResult | None = None

        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(self.downloader.download, url, media_kind),
                timeout=self.settings.download_timeout_seconds,
            )
            await self._send_result(update, context, result, status_message_id)
        except asyncio.TimeoutError:
            await self._edit_status(context, chat_id, status_message_id, "Download timed out. Try a shorter video.")
        except DownloadTooLarge as exc:
            await self._edit_status(
                context,
                chat_id,
                status_message_id,
                f"The downloaded file is {self._mb(exc.file_size)} MB, above the {self.settings.max_upload_mb} MB limit.",
            )
        except DownloadError as exc:
            logger.info("Download failed for %s: %s", url, exc)
            await self._edit_status(context, chat_id, status_message_id, f"Could not download that link: {exc}")
        except TelegramError as exc:
            logger.warning("Telegram upload failed: %s", exc)
            await self._edit_status(context, chat_id, status_message_id, f"Telegram could not send the file: {exc}")
        finally:
            action_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await action_task
            if result:
                result.cleanup()

    async def _send_result(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        result: DownloadResult,
        status_message_id: int,
    ) -> None:
        assert update.message is not None
        chat_id = update.effective_chat.id if update.effective_chat else update.message.chat_id

        await self._edit_status(context, chat_id, status_message_id, f"Uploading {self._mb(result.file_size)} MB...")

        caption = self._caption(result)
        suffix = result.file_path.suffix.lower()

        try:
            if result.media_kind == "voice":
                with result.file_path.open("rb") as media:
                    await update.message.reply_voice(
                        voice=media,
                        caption=caption,
                        duration=result.duration,
                        read_timeout=120,
                        write_timeout=120,
                        connect_timeout=30,
                    )
            elif result.media_kind == "audio":
                with result.file_path.open("rb") as media:
                    await update.message.reply_audio(
                        audio=media,
                        caption=caption,
                        title=result.title[:64],
                        duration=result.duration,
                        read_timeout=120,
                        write_timeout=120,
                        connect_timeout=30,
                    )
            elif suffix in {".mp4", ".m4v"}:
                with result.file_path.open("rb") as media:
                    await update.message.reply_video(
                        video=media,
                        caption=caption,
                        supports_streaming=True,
                        read_timeout=120,
                        write_timeout=120,
                        connect_timeout=30,
                    )
            else:
                await self._reply_document(update, result.file_path, caption)
        except TelegramError:
            logger.info("native media send failed; retrying as document")
            await self._reply_document(update, result.file_path, caption)

        await self._edit_status(context, chat_id, status_message_id, "Done.")

    async def _reply_document(self, update: Update, file_path: Path, caption: str) -> None:
        assert update.message is not None
        with file_path.open("rb") as media:
            await update.message.reply_document(
                document=media,
                caption=caption,
                read_timeout=120,
                write_timeout=120,
                connect_timeout=30,
            )

    async def _edit_status(
        self,
        context: ContextTypes.DEFAULT_TYPE,
        chat_id: int,
        message_id: int,
        text: str,
    ) -> None:
        with contextlib.suppress(TelegramError):
            await context.bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=text[:4096])

    async def _chat_action_loop(
        self,
        context: ContextTypes.DEFAULT_TYPE,
        chat_id: int,
        action: str,
    ) -> None:
        while True:
            with contextlib.suppress(TelegramError):
                await context.bot.send_chat_action(chat_id=chat_id, action=action)
            await asyncio.sleep(4)

    def _is_authorized(self, update: Update) -> bool:
        if not self.settings.bot_owner_ids:
            return True
        user_id = update.effective_user.id if update.effective_user else None
        return user_id in self.settings.bot_owner_ids

    def _caption(self, result: DownloadResult) -> str:
        caption = result.title.strip() or "Downloaded video"
        if result.duration:
            caption = f"{caption}\nDuration: {self._duration(result.duration)}"
        return caption[:1024]

    def _duration(self, seconds: int) -> str:
        minutes, sec = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)
        if hours:
            return f"{hours:d}:{minutes:02d}:{sec:02d}"
        return f"{minutes:d}:{sec:02d}"

    def _mb(self, size_bytes: int) -> str:
        return f"{size_bytes / 1024 / 1024:.1f}"

    def _media_label(self, media_kind: MediaKind) -> str:
        if media_kind == "audio":
            return "audio"
        if media_kind == "voice":
            return "voice message"
        return "video"

    def _chat_action(self, media_kind: MediaKind) -> str:
        if media_kind == "voice":
            return ChatAction.UPLOAD_VOICE
        if media_kind == "audio":
            return ChatAction.UPLOAD_DOCUMENT
        return ChatAction.UPLOAD_VIDEO


def build_application(settings: Settings) -> Application:
    telegram_bot = TelegramVideoBot(settings)

    builder = Application.builder().token(settings.telegram_bot_token)
    if settings.telegram_api_base_url:
        builder = builder.base_url(settings.telegram_api_base_url)
    if settings.telegram_api_base_file_url:
        builder = builder.base_file_url(settings.telegram_api_base_file_url)

    application = builder.concurrent_updates(settings.max_concurrent_downloads).build()
    application.add_handler(CommandHandler("start", telegram_bot.start))
    application.add_handler(CommandHandler("help", telegram_bot.help))
    application.add_handler(CommandHandler("status", telegram_bot.status))
    application.add_handler(CommandHandler("audio", telegram_bot.audio))
    application.add_handler(CommandHandler("voice", telegram_bot.voice))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, telegram_bot.handle_message))
    return application


def run() -> None:
    load_dotenv()

    try:
        settings = Settings.from_env()
    except ConfigError as exc:
        raise SystemExit(f"Configuration error: {exc}") from exc

    settings.download_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Starting Telegram video downloader bot")
    build_application(settings).run_polling(allowed_updates=Update.ALL_TYPES)
