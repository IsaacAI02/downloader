from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from video_downloader_bot.config import ConfigError, Settings


class ConfigTests(unittest.TestCase):
    def test_requires_token(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ConfigError):
                Settings.from_env()

    def test_parses_owner_ids_and_domains(self) -> None:
        with patch.dict(
            os.environ,
            {
                "TELEGRAM_BOT_TOKEN": "123:abc",
                "BOT_OWNER_IDS": "100, 200",
                "ALLOWED_DOMAINS": "YouTube.com, youtu.be",
            },
            clear=True,
        ):
            settings = Settings.from_env()

        self.assertEqual(settings.bot_owner_ids, (100, 200))
        self.assertEqual(settings.allowed_domains, ("youtube.com", "youtu.be"))

    def test_invalid_integer_raises(self) -> None:
        with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "123:abc", "MAX_UPLOAD_MB": "large"}, clear=True):
            with self.assertRaises(ConfigError):
                Settings.from_env()


if __name__ == "__main__":
    unittest.main()

