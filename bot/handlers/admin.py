"""Админка: статистика, очередь на проверке, решения по объявлениям, удаление по номеру."""

from aiogram import Bot, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, Message

from bot import keyboards, texts
from bot.db import ACTIVE, PENDING, REJECTED, Database
from bot.handlers.common import IsAdmin, show_screen
from bot.keyboards import AdminCb, ModAction, ModerateCb
from bot.notify import send_safely

# Сколько объявлений из очереди присылать за раз, чтобы не засыпать чат
QUEUE_BATCH_SIZE = 10

router = Router()
# Все обработчики этого файла работают только для администраторов
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())


@router.message(Command("admin"))
async def admin_panel(message: Message, db: Database) -> None:
    stats = await db.stats()
    await message.answer(
        texts.admin_stats(stats), reply_markup=keyboards.admin_menu(stats["ads"][PENDING])
    )


@router.callback_query(AdminCb.filter())
async def show_queue(callback: CallbackQuery, db: Database, bot: Bot) -> None:
    pending = await db.list_pending()
    if not pending:
        await callback.answer(texts.QUEUE_EMPTY, show_alert=True)
        return
    for ad in pending[:QUEUE_BATCH_SIZE]:
        await send_safely(
            bot, callback.from_user.id, texts.ad_for_review(ad), keyboards.moderation(ad["id"])
        )
    if len(pending) > QUEUE_BATCH_SIZE:
        left = len(pending) - QUEUE_BATCH_SIZE
        await send_safely(bot, callback.from_user.id, texts.queue_overflow(left))
    await callback.answer()


@router.callback_query(ModerateCb.filter())
async def moderate(
    callback: CallbackQuery, callback_data: ModerateCb, db: Database, bot: Bot
) -> None:
    ad = await db.get_ad(callback_data.id)
    # Другой администратор мог уже решить, или автор удалил объявление
    if ad is None or ad["status"] != PENDING:
        await callback.answer(texts.ALREADY_PROCESSED, show_alert=True)
        return
    approved = callback_data.action == ModAction.APPROVE
    await db.set_status(ad["id"], ACTIVE if approved else REJECTED)
    await send_safely(bot, ad["user_id"], texts.moderation_notice(ad, approved))
    await show_screen(
        callback, texts.moderation_result(ad, approved, callback.from_user.first_name)
    )


@router.message(Command("delete"))
async def delete_ad(message: Message, command: CommandObject, db: Database) -> None:
    if not command.args or not command.args.strip().isdigit():
        await message.answer(texts.DELETE_USAGE)
        return
    ad_id = int(command.args.strip())
    deleted = await db.delete_ad(ad_id)
    await message.answer(texts.ad_deleted(ad_id) if deleted else texts.AD_NOT_FOUND)
