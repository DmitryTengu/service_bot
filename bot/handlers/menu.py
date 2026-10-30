"""Команды /start и /menu, кнопки «Помощь» и «Открыть каталог»."""

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot import keyboards, texts
from bot.config import Settings
from bot.db import Database

router = Router()


@router.message(Command("start", "menu"))
async def open_menu(message: Message, state: FSMContext, db: Database, settings: Settings) -> None:
    """Сбрасывает незаконченный диалог, запоминает пользователя и показывает меню."""
    await state.clear()
    user = message.from_user
    if user is not None:
        await db.save_user(user.id, user.username, user.first_name)
    app_enabled = bool(settings.webapp_url)
    await message.answer(texts.WELCOME, reply_markup=keyboards.main_menu(app_enabled))
    if app_enabled:
        await message.answer(
            texts.OPEN_APP_PROMPT, reply_markup=keyboards.open_app(settings.webapp_url)
        )


@router.message(F.text == texts.BTN_OPEN_APP)
async def open_app(message: Message, state: FSMContext, settings: Settings) -> None:
    await state.clear()
    if settings.webapp_url:
        await message.answer(
            texts.OPEN_APP_PROMPT, reply_markup=keyboards.open_app(settings.webapp_url)
        )


@router.message(F.text == texts.BTN_HELP)
async def show_help(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(texts.HELP)
