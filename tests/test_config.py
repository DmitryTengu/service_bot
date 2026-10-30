"""Тесты чтения настроек из окружения (без чтения настоящего .env)."""

import asyncio
import os
import unittest
from unittest import mock

from bot import main as bot_main
from bot.config import DEFAULT_DB_PATH, DEFAULT_PORT, load_settings

BASE_ENV = {"BOT_TOKEN": "123456:TEST-TOKEN-NOT-REAL"}


def settings_from(**env):
    """Настройки из заданных переменных; файл .env подменён пустым."""
    with (
        mock.patch.dict(os.environ, {**BASE_ENV, **env}, clear=True),
        mock.patch("bot.config.load_dotenv"),
    ):
        return load_settings()


class SettingsTests(unittest.TestCase):
    def test_defaults_without_optional_values(self):
        settings = settings_from()
        self.assertEqual(settings.webapp_url, "")
        self.assertEqual(settings.port, DEFAULT_PORT)
        self.assertEqual(str(settings.db_path), DEFAULT_DB_PATH.replace("/", os.sep))
        self.assertFalse(settings.auto_approve)
        self.assertEqual(settings.admin_ids, frozenset())

    def test_empty_values_in_env_file_use_defaults(self):
        settings = settings_from(WEBAPP_URL="", PORT="", DB_PATH="")
        self.assertEqual((settings.webapp_url, settings.port), ("", DEFAULT_PORT))

    def test_webapp_url_must_be_https(self):
        for url in ("http://example.org", "example.org", "ftp://example.org"):
            with self.subTest(url=url), self.assertRaises(SystemExit):
                settings_from(WEBAPP_URL=url)

    def test_webapp_url_is_trimmed(self):
        settings = settings_from(WEBAPP_URL="  https://abc.example.org/  ")
        self.assertEqual(settings.webapp_url, "https://abc.example.org")

    def test_port_must_be_a_valid_number(self):
        for port in ("abc", "0", "70000", "-1", "80.5"):
            with self.subTest(port=port), self.assertRaises(SystemExit):
                settings_from(PORT=port)
        self.assertEqual(settings_from(PORT="9000").port, 9000)

    def test_token_is_required(self):
        with (
            mock.patch.dict(os.environ, {}, clear=True),
            mock.patch("bot.config.load_dotenv"),
            self.assertRaises(SystemExit),
        ):
            load_settings()


class BotStartTests(unittest.TestCase):
    def test_bot_refuses_to_start_without_webapp_url(self):
        # Падает до создания бота, поэтому в Telegram ничего не уходит
        with (
            mock.patch("bot.main.load_settings", return_value=settings_from()),
            self.assertRaises(SystemExit) as raised,
        ):
            asyncio.run(bot_main.main())
        self.assertIn("WEBAPP_URL", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
