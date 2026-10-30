"""Жалобы на объявления: уходят всем администраторам."""

from aiogram import Bot, Router
from aiogram.types import CallbackQuery

from bot import texts
from bot.config import Settings
from bot.db import ACTIVE, Database
from bot.keyboards import ReportCb
from bot.notify import notify_admins

router = Router()


@router.callback_query(ReportCb.filter())
async def report_ad(
    callback: CallbackQuery,
    callback_data: ReportCb,
    db: Database,
    bot: Bot,
    settings: Settings,
) -> None:
    ad = await db.get_ad(callback_data.id)
    if ad is None or ad["status"] != ACTIVE:
        await callback.answer(texts.AD_UNAVAILABLE, show_alert=True)
        return
    if not await db.add_report(callback.from_user.id, ad["id"]):
        await callback.answer(texts.REPORT_ALREADY_SENT, show_alert=True)
        return
    await notify_admins(bot, settings, texts.report_for_admin(ad, callback.from_user))
    await callback.answer(texts.REPORT_SENT, show_alert=True)
