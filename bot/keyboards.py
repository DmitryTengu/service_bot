"""Кнопки под сообщениями и данные, которые приходят при их нажатии."""

from enum import StrEnum

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from bot import texts


class ModAction(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"


class ModerateCb(CallbackData, prefix="mod"):
    """Решение администратора по объявлению на проверке."""

    action: ModAction
    id: int


class AdminCb(CallbackData, prefix="adm"):
    """Кнопка админ-панели (пока одна: показать очередь на проверке)."""


def _button(text: str, callback_data: CallbackData) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=callback_data.pack())


def open_app(url: str) -> InlineKeyboardMarkup:
    """Кнопка под сообщением, открывающая Mini App.

    Именно inline-кнопка: приложение, запущенное из кнопки нижней клавиатуры,
    не получает подписанных данных пользователя и не смогло бы войти.
    """
    app = InlineKeyboardButton(text=texts.BTN_OPEN_APP, web_app=WebAppInfo(url=url))
    return InlineKeyboardMarkup(inline_keyboard=[[app]])


def moderation(ad_id: int) -> InlineKeyboardMarkup:
    """Кнопки под объявлением на проверке: «Одобрить» и «Отклонить»."""
    approve = _button(texts.BTN_APPROVE, ModerateCb(action=ModAction.APPROVE, id=ad_id))
    reject = _button(texts.BTN_REJECT, ModerateCb(action=ModAction.REJECT, id=ad_id))
    return InlineKeyboardMarkup(inline_keyboard=[[approve], [reject]])


def admin_menu(pending: int) -> InlineKeyboardMarkup:
    """Админ-панель: кнопка очереди с числом объявлений."""
    return InlineKeyboardMarkup(inline_keyboard=[[_button(texts.queue_button(pending), AdminCb())]])
