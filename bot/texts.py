"""Все тексты бота. Пользовательские данные экранируются через html.escape,
чтобы нельзя было сломать HTML-разметку сообщения."""

from html import escape

from aiogram.types import User

from bot.categories import category_label
from bot.config import MAX_LIVE_ADS
from bot.db import ACTIVE, HIDDEN, PENDING, REJECTED
from bot.validators import DESCRIPTION_LIMIT, TITLE_LIMIT

# Подписи кнопок
BTN_SEARCH = "🔎 Найти услугу"
BTN_POST = "➕ Разместить услугу"
BTN_MY_ADS = "📋 Мои объявления"
BTN_HELP = "ℹ️ Помощь"
BTN_OPEN_APP = "🌐 Открыть каталог"
OPEN_APP_PROMPT = "🌐 Каталог в приложении удобнее.\nНажмите кнопку ниже."
BTN_BACK = "⬅️ Назад"
BTN_TO_CATEGORIES = "⬅️ К категориям"
BTN_PREV_PAGE = "◀️ Предыдущие"
BTN_NEXT_PAGE = "▶️ Следующие"
BTN_WRITE = "✉️ Написать"
BTN_REPORT = "⚠️ Пожаловаться"

# Самая длинная подпись inline-кнопки: длиннее читать неудобно и она обрезается на экране
BUTTON_TEXT_LIMIT = 40

WELCOME = "👋 Здравствуйте! Это каталог услуг.\nВыберите действие кнопками внизу."

HELP = (
    "<b>ℹ️ Как это работает</b>\n"
    "🔎 Найти услугу: выберите категорию.\n"
    "➕ Разместить услугу: ответьте на 6 вопросов.\n"
    "📋 Мои объявления: скрыть или удалить.\n"
    "⬅️ Назад и ❌ Отмена: кнопки внизу при размещении."
)

CHOOSE_CATEGORY = "Выберите категорию:"
CATEGORY_NOT_FOUND = "Такой категории нет."
AD_UNAVAILABLE = "Объявление недоступно."


# Кнопки диалога размещения
BTN_PUBLISH = "✅ Опубликовать"
BTN_CANCEL = "❌ Отмена"
BTN_SKIP = "⏭ Пропустить"

# Вопросы диалога размещения: один короткий вопрос на шаг
POST_INTRO = "➕ Разместим объявление.\nВнизу кнопки «Назад» и «Отмена»."
ASK_CATEGORY = "1/6 📂 Выберите категорию:"
ASK_TITLE = f"2/6 ✏️ Как называется услуга?\n({TITLE_LIMIT.min}–{TITLE_LIMIT.max} символов)"
ASK_DESCRIPTION = (
    f"3/6 📝 Опишите услугу коротко.\n({DESCRIPTION_LIMIT.min}–{DESCRIPTION_LIMIT.max} символов)"
)
ASK_PRICE = "4/6 💰 Сколько это стоит?\nНапример: от 20 BYN"
ASK_LOCATION = "5/6 📍 В каком районе или городе?"
ASK_PHONE = "6/6 📞 Телефон? Можно пропустить."
PHONE_SKIPPED = "📞 Без телефона"
MENU_HINT = "🏠 Выберите действие внизу."


def category_chosen(category_key: str) -> str:
    """Что остаётся на месте списка категорий после выбора."""
    return f"📂 {escape(category_label(category_key))}"


def ad_preview(ad: dict) -> str:
    """Предпросмотр: карточка, как её увидят другие, и напоминание про имя и контакты."""
    return f"👀 Проверьте объявление:\n{ad_card(ad)}\n⚠️ Имя и контакты увидят все."


LIMIT_REACHED = (
    f"🚫 Лимит объявлений: {MAX_LIVE_ADS}.\nСкройте или удалите одно в «Мои объявления»."
)
CANCELLED = "❌ Отменено."
NOTHING_TO_CANCEL = "Нечего отменять."
DIALOG_EXPIRED = "Диалог устарел.\nНачните заново: «Разместить услугу»."
EXPECT_TEXT = "✍️ Отправьте ответ текстом."
EXPECT_BUTTON = "👆 Выберите вариант кнопкой выше."


def input_error(error: Exception) -> str:
    """Сообщение о неверном вводе вместе с просьбой повторить."""
    return f"⚠️ {escape(str(error))}\nПопробуйте ещё раз."


def ad_published(ad_id: int, auto_approve: bool) -> str:
    """Что сказать автору после нажатия «Опубликовать»."""
    if auto_approve:
        return f"✅ №{ad_id} опубликовано."
    return f"✅ №{ad_id} отправлено на проверку.\nМы сообщим о решении."


def shorten(text: str, limit: int = BUTTON_TEXT_LIMIT) -> str:
    """Обрезает длинный текст до limit символов и добавляет «…»."""
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def category_page(category_key: str, page: int, pages: int, total: int) -> str:
    """Заголовок страницы списка объявлений."""
    title = f"<b>{escape(category_label(category_key))}</b>"
    if total == 0:
        return f"{title}\nПока нет объявлений."
    return f"{title}\nОбъявлений: {total} · страница {page + 1} из {pages}"


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


# ---------- статусы и «Мои объявления» ----------

_STATUS_NAMES = {
    PENDING: ("⏳", "на проверке"),
    ACTIVE: ("✅", "опубликовано"),
    REJECTED: ("❌", "отклонено"),
    HIDDEN: ("🙈", "скрыто"),
}

BTN_HIDE = "🙈 Скрыть"
BTN_SHOW = "👁 Показать"
BTN_DELETE = "🗑 Удалить"
BTN_CONFIRM_DELETE = "🗑 Да, удалить"

MY_ADS_TITLE = "📋 Ваши объявления:"
MY_ADS_EMPTY = "📭 У вас пока нет объявлений."


def status_icon(status: str) -> str:
    return _STATUS_NAMES[status][0]


def status_label(status: str) -> str:
    icon, name = _STATUS_NAMES[status]
    return f"{icon} {name}"


def my_ad_card(ad: dict) -> str:
    """Карточка в разделе «Мои объявления»: статус и номер первой строкой, дальше карточка."""
    return f"{status_label(ad['status'])} · №{ad['id']}\n{ad_card(ad)}"


def confirm_delete(ad_id: int) -> str:
    return f"🗑 Удалить №{ad_id}?\nОтменить это нельзя."


# ---------- модерация, жалобы и админка ----------

BTN_APPROVE = "✅ Одобрить"
BTN_REJECT = "❌ Отклонить"

ALREADY_PROCESSED = "Уже обработано или удалено."
QUEUE_EMPTY = "📭 Очередь пуста."
REPORT_SENT = "✅ Жалоба отправлена."
REPORT_ALREADY_SENT = "Вы уже жаловались на это объявление."
DELETE_USAGE = "Укажите номер: /delete 12"
AD_NOT_FOUND = "Не найдено."


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
    return f"❌ №{ad['id']} «{title}» отклонено.\nИсправьте и разместите заново."


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
