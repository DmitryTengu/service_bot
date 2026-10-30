"""Настройки бота. Все значения читаются из файла .env."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Сколько объявлений показывать на одной странице списка
PAGE_SIZE = 8
# Сколько объявлений (на проверке или опубликованных) может быть у одного человека
MAX_LIVE_ADS = 3

DEFAULT_DB_PATH = "data/bot.db"
DEFAULT_PORT = 8000

_TRUE_VALUES = {"1", "true", "yes", "on", "да"}


@dataclass(frozen=True)
class Settings:
    bot_token: str
    admin_ids: frozenset[int]
    db_path: Path
    auto_approve: bool
    # Публичный HTTPS-адрес Mini App; пустой, если веб-приложение не используется
    webapp_url: str = ""
    port: int = DEFAULT_PORT


def _parse_admin_ids(raw: str) -> frozenset[int]:
    """Превращает строку '1, 2, 3' в набор чисел, пустые и неверные части пропускает."""
    ids = set()
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit():
            ids.add(int(part))
    return frozenset(ids)


def _parse_webapp_url(raw: str) -> str:
    """Telegram открывает Mini App только по HTTPS, поэтому другой адрес считаем ошибкой."""
    url = raw.strip().rstrip("/")
    if url and not url.startswith("https://"):
        raise SystemExit("WEBAPP_URL должен начинаться с https:// (см. раздел Mini App в README).")
    return url


def _parse_port(raw: str) -> int:
    if not raw.strip():
        return DEFAULT_PORT
    if not raw.strip().isdigit() or not 0 < int(raw) < 65536:
        raise SystemExit("PORT должен быть числом от 1 до 65535.")
    return int(raw)


def load_settings() -> Settings:
    """Читает .env и собирает настройки. Без токена бот не запустится."""
    load_dotenv()
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise SystemExit("Не задан BOT_TOKEN. Впишите токен в файл .env (см. .env.example).")
    return Settings(
        bot_token=token,
        admin_ids=_parse_admin_ids(os.getenv("ADMIN_IDS", "")),
        # «or» нужен, чтобы пустая строка в .env тоже давала путь по умолчанию
        db_path=Path(os.getenv("DB_PATH") or DEFAULT_DB_PATH),
        auto_approve=os.getenv("AUTO_APPROVE", "0").strip().lower() in _TRUE_VALUES,
        webapp_url=_parse_webapp_url(os.getenv("WEBAPP_URL", "")),
        port=_parse_port(os.getenv("PORT", "")),
    )
