"""Поиск: категории, список объявлений по страницам и карточка объявления."""

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot import keyboards, texts
from bot.categories import get_category
from bot.db import ACTIVE, Database, page_count
from bot.handlers.common import show_screen
from bot.keyboards import AdCb, CategoryCb, MenuAction, MenuCb

router = Router()


@router.message(F.text == texts.BTN_SEARCH)
async def open_search(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(texts.CHOOSE_CATEGORY, reply_markup=keyboards.categories_menu())


@router.callback_query(MenuCb.filter(F.action == MenuAction.SEARCH))
async def show_categories(callback: CallbackQuery) -> None:
    await show_screen(callback, texts.CHOOSE_CATEGORY, keyboards.categories_menu())


@router.callback_query(CategoryCb.filter())
async def show_category(callback: CallbackQuery, callback_data: CategoryCb, db: Database) -> None:
    if get_category(callback_data.key) is None:
        await callback.answer(texts.CATEGORY_NOT_FOUND, show_alert=True)
        return

    ads, total = await db.list_by_category(callback_data.key, callback_data.page)
    # Если после удаления объявлений страница опустела, показываем последнюю существующую
    page = min(callback_data.page, page_count(total) - 1)
    if page != callback_data.page:
        ads, total = await db.list_by_category(callback_data.key, page)

    text = texts.category_page(callback_data.key, page, page_count(total), total)
    await show_screen(callback, text, keyboards.ads_page(ads, callback_data.key, page, total))


@router.callback_query(AdCb.filter())
async def show_ad(callback: CallbackQuery, callback_data: AdCb, db: Database) -> None:
    ad = await db.get_ad(callback_data.id)
    if ad is None or ad["status"] != ACTIVE:
        await callback.answer(texts.AD_UNAVAILABLE, show_alert=True)
        return
    await show_screen(callback, texts.ad_card(ad), keyboards.ad_card(ad, callback_data.page))
