"""Команды /start и /menu и ответ на всё остальное: всё делается в Mini App."""

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove

from bot import keyboards, texts
from bot.config import Settings
from bot.db import Database

router = Router()


@router.message(Command("start", "menu"))
async def open_menu(message: Message, db: Database, settings: Settings) -> None:
    """Запоминает пользователя и даёт кнопку каталога.

    ReplyKeyboardRemove убирает нижние кнопки, оставшиеся от прежней версии бота.
    """
    user = message.from_user
    if user is not None:
        await db.save_user(user.id, user.username, user.first_name)
    await message.answer(texts.WELCOME, reply_markup=ReplyKeyboardRemove())
    await message.answer(
        texts.OPEN_APP_PROMPT, reply_markup=keyboards.open_app(settings.webapp_url)
    )


@router.message()
async def point_to_app(message: Message, settings: Settings) -> None:
    """Любое другое сообщение: в чате ничего не делается, только в каталоге."""
    await message.answer(texts.MENU_HINT, reply_markup=keyboards.open_app(settings.webapp_url))


@router.callback_query()
async def outdated_button(callback: CallbackQuery) -> None:
    """Кнопки под старыми сообщениями больше ничего не делают; без ответа они бы «крутились»."""
    await callback.answer(texts.BUTTON_OUTDATED, show_alert=True)
