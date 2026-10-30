"""Отправка сообщений не в ответ на действие человека: администраторам и авторам."""

import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import InlineKeyboardMarkup

from bot.config import Settings

logger = logging.getLogger(__name__)


async def send_safely(
    bot: Bot, chat_id: int, text: str, markup: InlineKeyboardMarkup | None = None
) -> bool:
    """Отправляет сообщение; если не вышло (человек заблокировал бота), пишет в лог и идёт дальше.

    Одна неудачная отправка не должна ломать модерацию или рассылку остальным администраторам.
    """
    try:
        await bot.send_message(chat_id, text, reply_markup=markup)
    except TelegramAPIError as error:
        logger.warning("Не удалось отправить сообщение в чат %s: %s", chat_id, error)
        return False
    return True


async def notify_admins(
    bot: Bot, settings: Settings, text: str, markup: InlineKeyboardMarkup | None = None
) -> None:
    """Отправляет сообщение каждому администратору."""
    for admin_id in settings.admin_ids:
        await send_safely(bot, admin_id, text, markup)
