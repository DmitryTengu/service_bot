"""Размещение объявления: пошаговый диалог, предпросмотр и публикация."""

from collections.abc import Callable
from dataclasses import dataclass

from aiogram import Bot, F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message, User

from bot import keyboards, texts
from bot.categories import get_category
from bot.config import MAX_LIVE_ADS, Settings
from bot.db import Database, LimitReached
from bot.handlers.common import show_screen
from bot.keyboards import PickCategoryCb, PostAction, PostCb
from bot.notify import notify_admins
from bot.validators import (
    ValidationError,
    validate_description,
    validate_location,
    validate_phone,
    validate_price,
    validate_title,
)

router = Router()

# Текст, не начинающийся с «/»: команды (/menu, /admin) обрабатываются в других местах
PLAIN_TEXT = (F.text, ~F.text.startswith("/"))


class PostForm(StatesGroup):
    category = State()
    title = State()
    description = State()
    price = State()
    location = State()
    phone = State()
    confirm = State()


# Порядок шагов: по нему кнопка «Назад» находит предыдущий вопрос
_FLOW = [
    PostForm.category,
    PostForm.title,
    PostForm.description,
    PostForm.price,
    PostForm.location,
    PostForm.phone,
    PostForm.confirm,
]
_FLOW_NAMES = [step.state for step in _FLOW]

# Вопрос каждого шага и кнопки под ним. У шага confirm вопроса нет: там предпросмотр
_QUESTIONS: dict[str, tuple[str, InlineKeyboardMarkup | None]] = {
    PostForm.category.state: (texts.ASK_CATEGORY, keyboards.post_categories()),
    PostForm.title.state: (texts.ASK_TITLE, None),
    PostForm.description.state: (texts.ASK_DESCRIPTION, None),
    PostForm.price.state: (texts.ASK_PRICE, None),
    PostForm.location.state: (texts.ASK_LOCATION, None),
    PostForm.phone.state: (texts.ASK_PHONE, keyboards.skip_phone()),
}


@dataclass(frozen=True)
class TextStep:
    """Шаг, где человек вводит текст: какое поле заполняем, как проверить, куда дальше."""

    field: str
    validate: Callable[[str], str]
    next_state: State


_TEXT_STEPS = {
    PostForm.title.state: TextStep("title", validate_title, PostForm.description),
    PostForm.description.state: TextStep("description", validate_description, PostForm.price),
    PostForm.price.state: TextStep("price", validate_price, PostForm.location),
    PostForm.location.state: TextStep("location", validate_location, PostForm.phone),
    PostForm.phone.state: TextStep("phone", validate_phone, PostForm.confirm),
}


def _build_preview(data: dict, user: User) -> tuple[str, InlineKeyboardMarkup]:
    """Предпросмотр: та же карточка, что увидят другие, плюс напоминание и кнопка."""
    ad = {**data, "author_name": user.first_name, "author_username": user.username}
    return texts.ad_preview(ad), keyboards.confirm_post()


async def _ask(bot: Bot, chat_id: int, state: FSMContext, new_state: State, user: User) -> None:
    """Переходит к шагу new_state и задаёт его вопрос; на последнем шаге показывает предпросмотр."""
    await state.set_state(new_state)
    if new_state.state == PostForm.confirm.state:
        text, markup = _build_preview(await state.get_data(), user)
    else:
        text, markup = _QUESTIONS[new_state.state]
    await bot.send_message(chat_id, text, reply_markup=markup)


async def _cancel(message: Message, state: FSMContext, settings: Settings) -> None:
    """Выходит из диалога и возвращает нижнее главное меню."""
    await state.clear()
    menu = keyboards.main_menu(bool(settings.webapp_url))
    await message.answer(texts.CANCELLED, reply_markup=menu)


async def _finish(callback: CallbackQuery, bot: Bot, settings: Settings, text: str) -> None:
    """Показывает итог на месте предпросмотра и возвращает нижнее главное меню."""
    await show_screen(callback, text)
    menu = keyboards.main_menu(bool(settings.webapp_url))
    await bot.send_message(callback.from_user.id, texts.MENU_HINT, reply_markup=menu)


# ---------- начало, отмена и «Назад» ----------


@router.message(F.text == texts.BTN_POST)
async def start_post(message: Message, state: FSMContext, db: Database, bot: Bot) -> None:
    await state.clear()
    if await db.count_live_ads(message.from_user.id) >= MAX_LIVE_ADS:
        await message.answer(texts.LIMIT_REACHED)
        return
    # Нижние кнопки «Назад» и «Отмена» включаются на всё время диалога
    await message.answer(texts.POST_INTRO, reply_markup=keyboards.dialog_nav())
    await _ask(bot, message.chat.id, state, PostForm.category, message.from_user)


@router.message(Command("cancel"))
@router.message(StateFilter(PostForm), F.text == texts.BTN_CANCEL)
async def cancel_dialog(message: Message, state: FSMContext, settings: Settings) -> None:
    if await state.get_state() is None:
        await message.answer(texts.NOTHING_TO_CANCEL)
        return
    await _cancel(message, state, settings)


@router.message(StateFilter(PostForm), F.text == texts.BTN_BACK)
async def go_back(message: Message, state: FSMContext, bot: Bot, settings: Settings) -> None:
    index = _FLOW_NAMES.index(await state.get_state())
    if index == 0:
        # Назад с первого вопроса означает выйти из размещения
        await _cancel(message, state, settings)
        return
    await _ask(bot, message.chat.id, state, _FLOW[index - 1], message.from_user)


# ---------- шаги диалога ----------


@router.callback_query(PickCategoryCb.filter(), PostForm.category)
async def pick_category(
    callback: CallbackQuery, callback_data: PickCategoryCb, state: FSMContext, bot: Bot
) -> None:
    if get_category(callback_data.key) is None:
        await callback.answer(texts.CATEGORY_NOT_FOUND, show_alert=True)
        return
    await state.update_data(category=callback_data.key)
    # Список заменяется выбранной категорией, чтобы старые кнопки не оставались
    await show_screen(callback, texts.category_chosen(callback_data.key))
    await _ask(bot, callback.from_user.id, state, PostForm.title, callback.from_user)


@router.message(StateFilter(*_TEXT_STEPS), *PLAIN_TEXT)
async def take_text(message: Message, state: FSMContext, bot: Bot) -> None:
    step = _TEXT_STEPS[await state.get_state()]
    try:
        value = step.validate(message.text)
    except ValidationError as error:
        await message.answer(texts.input_error(error))
        return
    await state.update_data({step.field: value})
    await _ask(bot, message.chat.id, state, step.next_state, message.from_user)


@router.callback_query(PostCb.filter(F.action == PostAction.SKIP_PHONE), PostForm.phone)
async def skip_phone(callback: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await state.update_data(phone=None)
    await show_screen(callback, texts.PHONE_SKIPPED)
    await _ask(bot, callback.from_user.id, state, PostForm.confirm, callback.from_user)


# ---------- публикация ----------


@router.callback_query(PostCb.filter(F.action == PostAction.PUBLISH), PostForm.confirm)
async def publish(
    callback: CallbackQuery, state: FSMContext, db: Database, bot: Bot, settings: Settings
) -> None:
    data = await state.get_data()
    await state.clear()
    user = callback.from_user
    await db.save_user(user.id, user.username, user.first_name)
    try:
        ad_id = await db.create_ad(user.id, data, settings.auto_approve)
    except LimitReached:
        await _finish(callback, bot, settings, texts.LIMIT_REACHED)
        return
    if not settings.auto_approve:
        ad = await db.get_ad(ad_id)
        await notify_admins(bot, settings, texts.ad_for_review(ad), keyboards.moderation(ad_id))
    await _finish(callback, bot, settings, texts.ad_published(ad_id, settings.auto_approve))


# ---------- запасные ответы, если человек пишет не то, что ждёт диалог ----------


@router.message(StateFilter(PostForm.category, PostForm.confirm), *PLAIN_TEXT)
async def expect_button(message: Message) -> None:
    await message.answer(texts.EXPECT_BUTTON)


@router.message(StateFilter(PostForm), ~F.text)
async def expect_text(message: Message) -> None:
    await message.answer(texts.EXPECT_TEXT)


@router.callback_query(PostCb.filter())
@router.callback_query(PickCategoryCb.filter())
async def dialog_expired(callback: CallbackQuery) -> None:
    """Кнопка из старого сообщения, когда диалог уже закончился."""
    await callback.answer(texts.DIALOG_EXPIRED, show_alert=True)
