"""Точка входа: python -m bot.main"""

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand, MenuButtonWebApp, WebAppInfo

from bot.config import load_settings
from bot.db import Database
from bot.handlers import ROUTERS

logger = logging.getLogger(__name__)

# Меню команд рядом с полем ввода: короткие русские названия вместо набора команд
BOT_COMMANDS = [BotCommand(command="menu", description="Открыть каталог")]
MISSING_WEBAPP_URL = (
    "Не задан WEBAPP_URL. Всё делается в Mini App, без него боту нечего показать "
    "(см. раздел Mini App в README)."
)


def _app_menu_button(url: str) -> MenuButtonWebApp:
    """Кнопка рядом с полем ввода, которая открывает Mini App (подпись до 16 символов)."""
    return MenuButtonWebApp(text="Каталог", web_app=WebAppInfo(url=url))


async def main() -> None:
    settings = load_settings()
    if not settings.webapp_url:
        raise SystemExit(MISSING_WEBAPP_URL)
    if not settings.auto_approve and not settings.admin_ids:
        logger.warning("ADMIN_IDS пуст, а AUTO_APPROVE выключен: проверять объявления некому.")
    db = Database(settings.db_path)
    await db.init()

    # HTML-разметка включена везде; пользовательский текст экранируется в texts.py
    bot = Bot(settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    # db и settings становятся доступны обработчикам по имени параметра
    dispatcher = Dispatcher(db=db, settings=settings)
    dispatcher.include_routers(*ROUTERS)
    await bot.set_my_commands(BOT_COMMANDS)
    await bot.set_chat_menu_button(menu_button=_app_menu_button(settings.webapp_url))
    await dispatcher.start_polling(bot)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
