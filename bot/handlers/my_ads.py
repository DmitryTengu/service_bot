"""«Мои объявления»: список, скрыть, показать и удалить."""

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from bot import keyboards, texts
from bot.db import Database, LimitReached
from bot.handlers.common import show_screen
from bot.keyboards import MenuAction, MenuCb, MyAdAction, MyAdCb

router = Router()


async def _own_ad(callback: CallbackQuery, callback_data: MyAdCb, db: Database) -> dict | None:
    """Объявление, если оно существует и принадлежит нажавшему; иначе показывает сообщение."""
    ad = await db.get_ad(callback_data.id)
    if ad is None or ad["user_id"] != callback.from_user.id:
        await callback.answer(texts.AD_UNAVAILABLE, show_alert=True)
        return None
    return ad


async def _show_ad(callback: CallbackQuery, ad: dict) -> None:
    await show_screen(callback, texts.my_ad_card(ad), keyboards.my_ad_actions(ad))


async def _list_screen(db: Database, user_id: int) -> tuple[str, InlineKeyboardMarkup]:
    """Текст и кнопки списка объявлений человека."""
    ads = await db.list_by_user(user_id)
    text = texts.MY_ADS_TITLE if ads else texts.MY_ADS_EMPTY
    return text, keyboards.my_ads_list(ads)


async def _show_list(callback: CallbackQuery, db: Database) -> None:
    text, markup = await _list_screen(db, callback.from_user.id)
    await show_screen(callback, text, markup)


async def _switch_visibility(
    callback: CallbackQuery, callback_data: MyAdCb, db: Database, hidden: bool
) -> None:
    """Скрывает или показывает объявление и обновляет экран (правила: Database.set_hidden)."""
    try:
        ad = await db.set_hidden(callback_data.id, callback.from_user.id, hidden)
    except LimitReached:
        await callback.answer(texts.LIMIT_REACHED, show_alert=True)
        return
    if ad is None:
        await callback.answer(texts.AD_UNAVAILABLE, show_alert=True)
        return
    await _show_ad(callback, ad)


@router.message(F.text == texts.BTN_MY_ADS)
async def open_my_ads(message: Message, state: FSMContext, db: Database) -> None:
    await state.clear()
    text, markup = await _list_screen(db, message.from_user.id)
    await message.answer(text, reply_markup=markup)


@router.callback_query(MenuCb.filter(F.action == MenuAction.MY_ADS))
async def show_my_ads(callback: CallbackQuery, db: Database) -> None:
    await _show_list(callback, db)


@router.callback_query(MyAdCb.filter(F.action == MyAdAction.OPEN))
async def open_ad(callback: CallbackQuery, callback_data: MyAdCb, db: Database) -> None:
    ad = await _own_ad(callback, callback_data, db)
    if ad is not None:
        await _show_ad(callback, ad)


@router.callback_query(MyAdCb.filter(F.action == MyAdAction.HIDE))
async def hide_ad(callback: CallbackQuery, callback_data: MyAdCb, db: Database) -> None:
    await _switch_visibility(callback, callback_data, db, hidden=True)


@router.callback_query(MyAdCb.filter(F.action == MyAdAction.SHOW))
async def show_ad(callback: CallbackQuery, callback_data: MyAdCb, db: Database) -> None:
    await _switch_visibility(callback, callback_data, db, hidden=False)


@router.callback_query(MyAdCb.filter(F.action == MyAdAction.ASK_DELETE))
async def ask_delete(callback: CallbackQuery, callback_data: MyAdCb, db: Database) -> None:
    if await _own_ad(callback, callback_data, db) is not None:
        await show_screen(
            callback,
            texts.confirm_delete(callback_data.id),
            keyboards.confirm_delete(callback_data.id),
        )


@router.callback_query(MyAdCb.filter(F.action == MyAdAction.DELETE))
async def delete_ad(callback: CallbackQuery, callback_data: MyAdCb, db: Database) -> None:
    if await _own_ad(callback, callback_data, db) is not None:
        await db.delete_ad(callback_data.id, owner_id=callback.from_user.id)
        await _show_list(callback, db)
