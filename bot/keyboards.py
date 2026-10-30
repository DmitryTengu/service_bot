"""Кнопки под сообщениями и данные, которые приходят при их нажатии."""

from collections.abc import Callable
from enum import StrEnum

from aiogram.filters.callback_data import CallbackData
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    WebAppInfo,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from bot import texts
from bot.categories import CATEGORIES
from bot.db import ACTIVE, HIDDEN, page_count


class MenuAction(StrEnum):
    SEARCH = "search"
    MY_ADS = "my"


class MenuCb(CallbackData, prefix="menu"):
    """Возврат к списку категорий или к списку своих объявлений (кнопки «Назад»)."""

    action: MenuAction


class CategoryCb(CallbackData, prefix="cat"):
    """Открыть страницу списка объявлений категории."""

    key: str
    page: int = 0


class AdCb(CallbackData, prefix="ad"):
    """Открыть карточку объявления; page нужна, чтобы кнопка «Назад» вернула на ту же страницу."""

    id: int
    page: int = 0


class ReportCb(CallbackData, prefix="rep"):
    """Пожаловаться на объявление."""

    id: int


class PostAction(StrEnum):
    PUBLISH = "publish"
    SKIP_PHONE = "skip_phone"


class PostCb(CallbackData, prefix="post"):
    """Нажатие кнопки в диалоге размещения."""

    action: PostAction


class PickCategoryCb(CallbackData, prefix="pick"):
    """Выбор категории для нового объявления."""

    key: str


class ModAction(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"


class ModerateCb(CallbackData, prefix="mod"):
    """Решение администратора по объявлению на проверке."""

    action: ModAction
    id: int


class AdminCb(CallbackData, prefix="adm"):
    """Кнопка админ-панели (пока одна: показать очередь на проверке)."""


class MyAdAction(StrEnum):
    OPEN = "open"
    HIDE = "hide"
    SHOW = "show"
    ASK_DELETE = "ask_delete"
    DELETE = "delete"


class MyAdCb(CallbackData, prefix="my"):
    """Действие автора со своим объявлением."""

    action: MyAdAction
    id: int


def _button(text: str, callback_data: CallbackData) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=callback_data.pack())


def main_menu(app_enabled: bool = False) -> ReplyKeyboardMarkup:
    """Главное меню: постоянные крупные кнопки внизу экрана, по одной в строке.

    resize_keyboard не включаем: без него Telegram рисует кнопки высокими.
    Кнопка «Открыть каталог» нужна только когда задан WEBAPP_URL (app_enabled).
    """
    labels = [texts.BTN_SEARCH, texts.BTN_POST, texts.BTN_MY_ADS, texts.BTN_HELP]
    if app_enabled:
        labels.insert(0, texts.BTN_OPEN_APP)
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=label)] for label in labels], is_persistent=True
    )


def _category_grid(callback_for: Callable[[str], CallbackData]) -> InlineKeyboardBuilder:
    """Категории по одной в ряд; что произойдёт при нажатии, решает callback_for."""
    builder = InlineKeyboardBuilder()
    for category in CATEGORIES:
        builder.button(text=texts.shorten(category.label), callback_data=callback_for(category.key))
    builder.adjust(1)
    return builder


def categories_menu() -> InlineKeyboardMarkup:
    """Категории для поиска."""
    return _category_grid(lambda key: CategoryCb(key=key)).as_markup()


def dialog_nav() -> ReplyKeyboardMarkup:
    """Нижние кнопки на время размещения: «Назад» и «Отмена», по одной в строке."""
    labels = (texts.BTN_BACK, texts.BTN_CANCEL)
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=label)] for label in labels], is_persistent=True
    )


def open_app(url: str) -> InlineKeyboardMarkup:
    """Кнопка под сообщением, открывающая Mini App.

    Именно inline-кнопка: приложение, запущенное из кнопки нижней клавиатуры,
    не получает подписанных данных пользователя и не смогло бы войти.
    """
    app = InlineKeyboardButton(text=texts.BTN_OPEN_APP, web_app=WebAppInfo(url=url))
    return InlineKeyboardMarkup(inline_keyboard=[[app]])


def post_categories() -> InlineKeyboardMarkup:
    """Категории для нового объявления."""
    return _category_grid(lambda key: PickCategoryCb(key=key)).as_markup()


def skip_phone() -> InlineKeyboardMarkup:
    """Кнопка шага «Телефон»: «Пропустить»."""
    skip = _button(texts.BTN_SKIP, PostCb(action=PostAction.SKIP_PHONE))
    return InlineKeyboardMarkup(inline_keyboard=[[skip]])


def confirm_post() -> InlineKeyboardMarkup:
    """Кнопка под предпросмотром: «Опубликовать»."""
    publish = _button(texts.BTN_PUBLISH, PostCb(action=PostAction.PUBLISH))
    return InlineKeyboardMarkup(inline_keyboard=[[publish]])


def ads_page(ads: list[dict], category_key: str, page: int, total: int) -> InlineKeyboardMarkup:
    """Объявления страницы кнопками, листание вперёд и назад, возврат к категориям."""
    builder = InlineKeyboardBuilder()
    for ad in ads:
        label = texts.shorten(f"{ad['title']} · {ad['price']}")
        builder.button(text=label, callback_data=AdCb(id=ad["id"], page=page))
    builder.adjust(1)

    # Каждая кнопка в своей строке: так крупнее и по ним проще попасть
    if page > 0:
        builder.row(_button(texts.BTN_PREV_PAGE, CategoryCb(key=category_key, page=page - 1)))
    if page + 1 < page_count(total):
        builder.row(_button(texts.BTN_NEXT_PAGE, CategoryCb(key=category_key, page=page + 1)))
    builder.row(_button(texts.BTN_TO_CATEGORIES, MenuCb(action=MenuAction.SEARCH)))
    return builder.as_markup()


def moderation(ad_id: int) -> InlineKeyboardMarkup:
    """Кнопки под объявлением на проверке: «Одобрить» и «Отклонить»."""
    approve = _button(texts.BTN_APPROVE, ModerateCb(action=ModAction.APPROVE, id=ad_id))
    reject = _button(texts.BTN_REJECT, ModerateCb(action=ModAction.REJECT, id=ad_id))
    return InlineKeyboardMarkup(inline_keyboard=[[approve], [reject]])


def admin_menu(pending: int) -> InlineKeyboardMarkup:
    """Админ-панель: кнопка очереди с числом объявлений."""
    return InlineKeyboardMarkup(inline_keyboard=[[_button(texts.queue_button(pending), AdminCb())]])


def my_ads_list(ads: list[dict]) -> InlineKeyboardMarkup:
    """Объявления автора кнопками со значком статуса."""
    builder = InlineKeyboardBuilder()
    for ad in ads:
        label = texts.shorten(f"{texts.status_icon(ad['status'])} №{ad['id']} {ad['title']}")
        builder.button(text=label, callback_data=MyAdCb(action=MyAdAction.OPEN, id=ad["id"]))
    builder.adjust(1)
    return builder.as_markup()


def my_ad_actions(ad: dict) -> InlineKeyboardMarkup:
    """Кнопки под своим объявлением по одной в ряд: «Скрыть» или «Показать», «Удалить», «Назад»."""
    rows = []
    if ad["status"] == ACTIVE:
        rows.append([_button(texts.BTN_HIDE, MyAdCb(action=MyAdAction.HIDE, id=ad["id"]))])
    if ad["status"] == HIDDEN:
        rows.append([_button(texts.BTN_SHOW, MyAdCb(action=MyAdAction.SHOW, id=ad["id"]))])
    rows.append([_button(texts.BTN_DELETE, MyAdCb(action=MyAdAction.ASK_DELETE, id=ad["id"]))])
    rows.append([_button(texts.BTN_BACK, MenuCb(action=MenuAction.MY_ADS))])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def confirm_delete(ad_id: int) -> InlineKeyboardMarkup:
    """Подтверждение удаления: «Да, удалить» и «Отмена» (возврат к объявлению)."""
    delete = _button(texts.BTN_CONFIRM_DELETE, MyAdCb(action=MyAdAction.DELETE, id=ad_id))
    cancel = _button(texts.BTN_CANCEL, MyAdCb(action=MyAdAction.OPEN, id=ad_id))
    return InlineKeyboardMarkup(inline_keyboard=[[delete], [cancel]])


def _author_link(ad: dict) -> str:
    """Ссылка на автора: по @username, а без него по номеру пользователя."""
    if ad["author_username"]:
        return f"https://t.me/{ad['author_username']}"
    return f"tg://user?id={ad['user_id']}"


def ad_card(ad: dict, page: int) -> InlineKeyboardMarkup:
    """Кнопки под карточкой по одной в ряд: «Написать», «Пожаловаться» и «Назад» к списку."""
    write = InlineKeyboardButton(text=texts.BTN_WRITE, url=_author_link(ad))
    report = _button(texts.BTN_REPORT, ReportCb(id=ad["id"]))
    back = _button(texts.BTN_BACK, CategoryCb(key=ad["category"], page=page))
    return InlineKeyboardMarkup(inline_keyboard=[[write], [report], [back]])
