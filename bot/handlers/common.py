"""Общие помощники для обработчиков."""

from aiogram.filters import Filter
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from bot.config import Settings


class IsAdmin(Filter):
    """Пропускает только администраторов из ADMIN_IDS; остальным бот не отвечает."""

    async def __call__(self, event: Message | CallbackQuery, settings: Settings) -> bool:
        return event.from_user is not None and event.from_user.id in settings.admin_ids


async def show_screen(
    callback: CallbackQuery, text: str, markup: InlineKeyboardMarkup | None = None
) -> None:
    """Заменяет текст и кнопки сообщения, под которым нажали кнопку (экран «меняется на месте»).

    Без markup кнопки у сообщения исчезают.
    """
    if isinstance(callback.message, Message):
        await callback.message.edit_text(text, reply_markup=markup)
    await callback.answer()
