"""Все тексты бота. Пользовательские данные экранируются через html.escape,
чтобы нельзя было сломать HTML-разметку сообщения."""

from html import escape

from aiogram.types import User

from bot.categories import category_label
from bot.db import ACTIVE, HIDDEN, PENDING, REJECTED

BTN_OPEN_APP = "🌐 Открыть каталог"

WELCOME = (
    "👋 Здравствуйте! Это каталог услуг.\n"
    "Искать услуги, размещать и менять свои объявления можно в каталоге."
)
OPEN_APP_PROMPT = "🌐 Нажмите кнопку ниже, чтобы открыть каталог."
MENU_HINT = "🌐 Всё делается в каталоге.\nНажмите кнопку ниже."
BUTTON_OUTDATED = "Эта кнопка устарела. Откройте каталог: /menu"


def person_label(name: str | None, username: str | None) -> str:
    """Имя человека и, если есть, его @username (уже с экранированием)."""
    name = escape(name or "Без имени")
    return f"{name} (@{escape(username)})" if username else name


def ad_card(ad: dict) -> str:
    """Короткая карточка, не больше 5 строк: главное (название и цена) в первой строке."""
    lines = [
        f"<b>{escape(ad['title'])}</b> · 💰 {escape(ad['price'])}",
        escape(ad["description"]),
        f"📍 {escape(ad['location'])}",
    ]
    if ad["phone"]:
        lines.append(f"📞 {escape(ad['phone'])}")
    lines.append(f"👤 {person_label(ad['author_name'], ad['author_username'])}")
    return "\n".join(lines)


# ---------- модерация, жалобы и админка ----------

_STATUS_NAMES = {
    PENDING: ("⏳", "на проверке"),
    ACTIVE: ("✅", "опубликовано"),
    REJECTED: ("❌", "отклонено"),
    HIDDEN: ("🙈", "скрыто"),
}

BTN_APPROVE = "✅ Одобрить"
BTN_REJECT = "❌ Отклонить"

ALREADY_PROCESSED = "Уже обработано или удалено."
QUEUE_EMPTY = "📭 Очередь пуста."
DELETE_USAGE = "Укажите номер: /delete 12"
AD_NOT_FOUND = "Не найдено."


def status_label(status: str) -> str:
    icon, name = _STATUS_NAMES[status]
    return f"{icon} {name}"


def queue_button(pending: int) -> str:
    return f"📥 На проверке: {pending}"


def queue_overflow(hidden: int) -> str:
    return f"…и ещё в очереди: {hidden}"


def ad_for_review(ad: dict) -> str:
    """Сообщение администратору о новом объявлении; категория в заголовке, её нет в карточке."""
    category = escape(category_label(ad["category"]))
    return f"🆕 №{ad['id']} ждёт проверки · {category}\n{ad_card(ad)}"


def moderation_result(ad: dict, approved: bool, admin_name: str) -> str:
    """Что остаётся в сообщении администратора после нажатия кнопки."""
    verdict = "✅ одобрено" if approved else "❌ отклонено"
    title = escape(ad["title"])
    return f"№{ad['id']} «{title}»: {verdict} ({escape(admin_name)})"


def moderation_notice(ad: dict, approved: bool) -> str:
    """Уведомление автору о решении."""
    title = escape(ad["title"])
    if approved:
        return f"✅ №{ad['id']} «{title}» опубликовано."
    return f"❌ №{ad['id']} «{title}» отклонено.\nИсправьте и разместите заново в каталоге."


def report_for_admin(ad: dict, reporter: User) -> str:
    """Жалоба на объявление: кто пожаловался, само объявление и как его удалить."""
    who = person_label(reporter.first_name, reporter.username)
    return (
        f"⚠️ Жалоба на №{ad['id']}\n"
        f"👤 От: {who}, id {reporter.id}\n"
        f"{ad_card(ad)}\n"
        f"🗑 Удалить: /delete {ad['id']}"
    )


def admin_stats(stats: dict) -> str:
    """Статистика для /admin."""
    lines = ["<b>🛠 Админ-панель</b>", f"👥 Пользователей: {stats['users']}"]
    lines += [f"{status_label(status)}: {count}" for status, count in stats["ads"].items()]
    lines.append("🗑 Удалить: /delete НОМЕР")
    return "\n".join(lines)


def ad_deleted(ad_id: int) -> str:
    return f"🗑 №{ad_id} удалено."
