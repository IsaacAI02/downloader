# Telegram Video Downloader Bot

A Telegram bot that accepts a video URL, downloads it with `yt-dlp`, and sends the file back to the chat as video, audio, or a Telegram voice message.

Use this only for videos you own, have permission to download, or are otherwise legally allowed to save. The bot does not bypass DRM, and you should respect each platform's terms.

## What It Supports

The downloader uses `yt-dlp`, which supports thousands of sites. In practice, support depends on the platform, public/private access, cookies, regional restrictions, and whether `ffmpeg` is installed.

The default format prefers a single MP4-like download that fits Telegram's public Bot API upload limit. Audio and voice-message conversion require `ffmpeg`; the project uses a bundled ffmpeg package locally, and Docker/Render install system ffmpeg.

## Quick Start on Windows

1. Install Python 3.11 or newer.
2. Create a bot with [@BotFather](https://t.me/BotFather) and copy the token.
3. Create and activate a virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

4. Copy the example env file and add your token:

```powershell
Copy-Item .env.example .env
notepad .env
```

5. Run the bot:

```powershell
python -m video_downloader_bot
```

Open Telegram, start your bot, and send it a video URL.

Commands:

```text
<url>          Download as video
/audio <url>   Download and send as MP3 audio
/voice <url>   Download and send as a Telegram voice message
```

## Docker

Docker is the easiest deployment path because the image includes `ffmpeg`.

```powershell
Copy-Item .env.example .env
notepad .env
docker compose up --build
```

## Deploy Online

The project includes a `Dockerfile`, `.dockerignore`, and `render.yaml` so it can run as a Render free web service.

Important: run only one copy of the bot at a time. The Render deployment uses Telegram webhooks; when it is live, stop the local polling bot on your PC.

### Render

1. Push this repository to GitHub.
2. Create a new Blueprint on Render and connect the repo.
3. When Render asks for `TELEGRAM_BOT_TOKEN`, paste your token as a secret value.
4. Deploy the `telegram-video-downloader-bot` web service.
5. Stop the local bot after the cloud service is live.

The included `render.yaml` uses Render's free web service plan and webhook mode. It is enough for light testing, but downloads can be slow because the free instance has limited CPU/RAM, and video bots can use bandwidth quickly. Render free web services can spin down after idle time; Telegram should retry webhook delivery when the service wakes up.

Do not upload `.env`; it is ignored by Git and Docker on purpose. For best security, regenerate the token in BotFather before deploying because the original token was shared in chat.

## Configuration

All settings are environment variables, usually stored in `.env`.

| Variable | Default | Purpose |
| --- | --- | --- |
| `TELEGRAM_BOT_TOKEN` | required | Bot token from BotFather. |
| `MAX_UPLOAD_MB` | `49` | Maximum file size the bot will send back. Keep below 50 MB for the public Bot API. |
| `MAX_CONCURRENT_DOWNLOADS` | `1` | Number of downloads to run at once. |
| `DOWNLOAD_TIMEOUT_SECONDS` | `600` | Per-download timeout. |
| `NETWORK_TIMEOUT_SECONDS` | `30` | Socket timeout used by `yt-dlp`. |
| `DOWNLOAD_DIR` | `downloads` | Temporary download storage. |
| `BOT_OWNER_IDS` | empty | Optional comma-separated Telegram user IDs allowed to use the bot. |
| `ALLOWED_DOMAINS` | empty | Optional allowlist, e.g. `youtube.com,youtu.be,vimeo.com`. |
| `BLOCKED_DOMAINS` | empty | Optional blocklist. |
| `ALLOW_PRIVATE_URLS` | `false` | Allows localhost/private IP URLs if set to `true`. Leave off for deployed bots. |
| `YTDLP_COOKIES_FILE` | empty | Optional cookies file for accounts/content you are authorized to access. |
| `YTDLP_USER_AGENT` | empty | Optional custom user agent. |
| `YTDLP_FORMAT` | empty | Optional yt-dlp format selector override. |
| `YTDLP_AUDIO_FORMAT` | empty | Optional yt-dlp audio format selector override. |
| `AUDIO_BITRATE_KBPS` | `128` | MP3 bitrate for `/audio`. |
| `VOICE_BITRATE_KBPS` | `48` | OGG/Opus bitrate for `/voice`. |
| `FFMPEG_LOCATION` | empty | Optional path to ffmpeg if it is not on `PATH`. |
| `WEBHOOK_URL` | empty | Public base URL for webhook mode. Render normally provides this automatically. |
| `WEBHOOK_PATH` | `telegram-webhook` | URL path used for Telegram webhook delivery. |
| `WEBHOOK_SECRET_TOKEN` | empty | Optional Telegram webhook secret; a token-derived secret is used if empty. |
| `PORT` | `10000` | HTTP port for webhook mode. Render sets this automatically for web services. |
| `TELEGRAM_API_BASE_URL` | empty | Optional local Bot API base URL. |
| `TELEGRAM_API_BASE_FILE_URL` | empty | Optional local Bot API file base URL. |

## Larger Files

Telegram's public Bot API currently documents 50 MB upload limits for videos and documents, so this project defaults to 49 MB. If you need files larger than that, Telegram documents that a local Bot API server can upload files up to 2000 MB. Set `MAX_UPLOAD_MB` higher and configure the local API base URLs in `.env` after you deploy that server.

## Useful Format Examples

Prefer MP4 up to 720p:

```env
YTDLP_FORMAT=best[height<=720][ext=mp4]/best[height<=720]/best
```

Use video+audio merging when `ffmpeg` is available:

```env
YTDLP_FORMAT=bestvideo[height<=720]+bestaudio/best[height<=720]/best
```

## Tests

The tests cover the local config and URL safety helpers:

```powershell
python -m unittest discover
```
