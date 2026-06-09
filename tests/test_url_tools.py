from __future__ import annotations

import unittest
from pathlib import Path

from video_downloader_bot.config import Settings
from video_downloader_bot.url_tools import domain_matches, extract_urls, is_private_hostname, validate_url


def settings(**overrides: object) -> Settings:
    values = {
        "telegram_bot_token": "token",
        "max_upload_mb": 45,
        "max_concurrent_downloads": 1,
        "download_timeout_seconds": 600,
        "network_timeout_seconds": 30,
        "download_dir": Path("downloads"),
        "bot_owner_ids": (),
        "allowed_domains": (),
        "blocked_domains": (),
        "allow_private_urls": False,
        "ytdlp_cookies_file": None,
        "ytdlp_user_agent": None,
        "ytdlp_format": None,
        "ytdlp_audio_format": None,
        "audio_bitrate_kbps": 128,
        "voice_bitrate_kbps": 48,
        "ffmpeg_location": None,
        "telegram_api_base_url": None,
        "telegram_api_base_file_url": None,
    }
    values.update(overrides)
    return Settings(**values)


class UrlToolsTests(unittest.TestCase):
    def test_extract_urls_strips_common_trailing_punctuation(self) -> None:
        self.assertEqual(extract_urls("watch https://example.com/video)."), ["https://example.com/video"])

    def test_domain_matches_subdomains(self) -> None:
        self.assertTrue(domain_matches("m.youtube.com", "youtube.com"))
        self.assertFalse(domain_matches("notyoutube.com", "youtube.com"))

    def test_private_hosts_are_blocked_by_default(self) -> None:
        result = validate_url("http://127.0.0.1/video", settings())
        self.assertFalse(result.ok)

    def test_allowed_domains_accepts_subdomain(self) -> None:
        result = validate_url("https://m.youtube.com/watch?v=x", settings(allowed_domains=("youtube.com",)))
        self.assertTrue(result.ok)

    def test_blocked_domains_rejects_subdomain(self) -> None:
        result = validate_url("https://sub.example.com/video", settings(blocked_domains=("example.com",)))
        self.assertFalse(result.ok)

    def test_private_hostname_detection(self) -> None:
        self.assertTrue(is_private_hostname("localhost"))
        self.assertTrue(is_private_hostname("10.1.2.3"))
        self.assertFalse(is_private_hostname("example.com"))


if __name__ == "__main__":
    unittest.main()
