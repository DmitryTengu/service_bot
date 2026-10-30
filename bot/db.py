"""Работа с базой SQLite. Все публичные методы асинхронные: настоящая работа с базой
идёт в отдельном потоке через asyncio.to_thread, чтобы бот не «зависал»."""

import asyncio
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from bot.config import MAX_LIVE_ADS, PAGE_SIZE

# Статусы объявления
PENDING = "pending"  # на проверке
ACTIVE = "active"  # опубликовано
REJECTED = "rejected"  # отклонено администратором
HIDDEN = "hidden"  # скрыто автором
STATUSES = (PENDING, ACTIVE, REJECTED, HIDDEN)
# Статусы, которые считаются в лимите объявлений на человека
LIVE_STATUSES = (PENDING, ACTIVE)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id         INTEGER PRIMARY KEY,
    username   TEXT,
    first_name TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS ads (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL REFERENCES users(id),
    category    TEXT NOT NULL,
    title       TEXT NOT NULL,
    description TEXT NOT NULL,
    price       TEXT NOT NULL,
    location    TEXT NOT NULL,
    phone       TEXT,
    status      TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_ads_category_status ON ads(category, status);
CREATE INDEX IF NOT EXISTS idx_ads_user ON ads(user_id);
CREATE TABLE IF NOT EXISTS reports (
    user_id INTEGER NOT NULL,
    ad_id   INTEGER NOT NULL,
    PRIMARY KEY (user_id, ad_id)
);
"""

# Объявление вместе с данными автора
_SELECT_AD = """
SELECT ads.*, users.username AS author_username, users.first_name AS author_name
FROM ads JOIN users ON users.id = ads.user_id
"""


def page_count(total: int) -> int:
    """Сколько страниц нужно для total объявлений (минимум одна, даже если список пуст)."""
    return max(1, -(-total // PAGE_SIZE))


class LimitReached(Exception):
    """У человека уже максимум объявлений на проверке и опубликованных."""


class Database:
    def __init__(self, path: Path | str):
        self.path = Path(path)

    # ---------- внутренние помощники ----------

    @contextmanager
    def _connect(self):
        """Открывает соединение, сохраняет изменения при успехе и всегда закрывает."""
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        # Встроенный регистр SQLite не понимает кириллицу, поэтому поиск идёт через свою функцию
        conn.create_function("fold", 1, str.casefold, deterministic=True)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    @staticmethod
    def _count_live(conn: sqlite3.Connection, user_id: int) -> int:
        marks = ",".join("?" * len(LIVE_STATUSES))
        row = conn.execute(
            f"SELECT COUNT(*) FROM ads WHERE user_id = ? AND status IN ({marks})",
            (user_id, *LIVE_STATUSES),
        ).fetchone()
        return row[0]

    # ---------- синхронные версии (их вызывают через to_thread) ----------

    def _init(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    def _save_user(self, user_id: int, username: str | None, first_name: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO users (id, username, first_name) VALUES (?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET username = excluded.username, "
                "first_name = excluded.first_name",
                (user_id, username, first_name),
            )

    def _create_ad(self, user_id: int, fields: dict, auto_approve: bool) -> int:
        with self._connect() as conn:
            if self._count_live(conn, user_id) >= MAX_LIVE_ADS:
                raise LimitReached
            cursor = conn.execute(
                "INSERT INTO ads (user_id, category, title, description, price, location,"
                " phone, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    user_id,
                    fields["category"],
                    fields["title"],
                    fields["description"],
                    fields["price"],
                    fields["location"],
                    fields.get("phone"),
                    ACTIVE if auto_approve else PENDING,
                ),
            )
            return cursor.lastrowid

    def _get_ad(self, ad_id: int) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(_SELECT_AD + " WHERE ads.id = ?", (ad_id,)).fetchone()
        return dict(row) if row else None

    def _set_status(self, ad_id: int, status: str, owner_id: int | None) -> bool:
        with self._connect() as conn:
            row = conn.execute("SELECT user_id, status FROM ads WHERE id = ?", (ad_id,)).fetchone()
            if row is None or (owner_id is not None and row["user_id"] != owner_id):
                return False
            # Возвращая объявление в «живые» статусы, проверяем лимит
            comes_back = status in LIVE_STATUSES and row["status"] not in LIVE_STATUSES
            if comes_back and self._count_live(conn, row["user_id"]) >= MAX_LIVE_ADS:
                raise LimitReached
            conn.execute("UPDATE ads SET status = ? WHERE id = ?", (status, ad_id))
            return True

    def _set_hidden(self, ad_id: int, owner_id: int, hidden: bool) -> dict | None:
        ad = self._get_ad(ad_id)
        if ad is None or ad["user_id"] != owner_id:
            return None
        current, new = (ACTIVE, HIDDEN) if hidden else (HIDDEN, ACTIVE)
        # Только опубликованное можно скрыть и только скрытое показать: отклонённое или
        # ожидающее проверки объявление этим способом в каталог не попадёт
        if ad["status"] == current:
            self._set_status(ad_id, new, owner_id)
            ad = self._get_ad(ad_id)
        return ad

    @staticmethod
    def _search_filter(category: str | None, query: str | None) -> tuple[str, list]:
        """Условие WHERE и его значения: опубликованные, по желанию категория и текст."""
        conditions, params = ["ads.status = ?"], [ACTIVE]
        if category:
            conditions.append("ads.category = ?")
            params.append(category)
        if query:
            # instr вместо LIKE: символы % и _ в запросе ищутся как обычный текст
            conditions.append("instr(fold(ads.title || ' ' || ads.description), ?) > 0")
            params.append(query.casefold())
        return " AND ".join(conditions), params

    def _search(self, category: str | None, query: str | None, page: int) -> tuple[list[dict], int]:
        where, params = self._search_filter(category, query)
        with self._connect() as conn:
            total = conn.execute(f"SELECT COUNT(*) FROM ads WHERE {where}", params).fetchone()[0]
            rows = conn.execute(
                f"{_SELECT_AD} WHERE {where} ORDER BY ads.id DESC LIMIT ? OFFSET ?",
                (*params, PAGE_SIZE, page * PAGE_SIZE),
            ).fetchall()
        return [dict(row) for row in rows], total

    def _list_by_user(self, user_id: int) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                _SELECT_AD + " WHERE ads.user_id = ? ORDER BY ads.id DESC", (user_id,)
            ).fetchall()
        return [dict(row) for row in rows]

    def _list_pending(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                _SELECT_AD + " WHERE ads.status = ? ORDER BY ads.id", (PENDING,)
            ).fetchall()
        return [dict(row) for row in rows]

    def _delete_ad(self, ad_id: int, owner_id: int | None) -> bool:
        query, params = "DELETE FROM ads WHERE id = ?", [ad_id]
        if owner_id is not None:
            query += " AND user_id = ?"
            params.append(owner_id)
        with self._connect() as conn:
            deleted = conn.execute(query, params).rowcount > 0
            if deleted:
                conn.execute("DELETE FROM reports WHERE ad_id = ?", (ad_id,))
            return deleted

    def _add_report(self, user_id: int, ad_id: int) -> bool:
        with self._connect() as conn:
            # Пара (человек, объявление) уникальна, поэтому повторная жалоба игнорируется
            cursor = conn.execute(
                "INSERT OR IGNORE INTO reports (user_id, ad_id) VALUES (?, ?)", (user_id, ad_id)
            )
            return cursor.rowcount > 0

    def _stats(self) -> dict:
        with self._connect() as conn:
            users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            by_status = {status: 0 for status in STATUSES}
            for row in conn.execute("SELECT status, COUNT(*) AS n FROM ads GROUP BY status"):
                by_status[row["status"]] = row["n"]
        return {"users": users, "ads": by_status}

    # ---------- асинхронный интерфейс для остального кода ----------

    async def init(self) -> None:
        """Создаёт папку и таблицы, если их ещё нет."""
        await asyncio.to_thread(self._init)

    async def save_user(self, user_id: int, username: str | None, first_name: str) -> None:
        """Запоминает пользователя или обновляет его имя."""
        await asyncio.to_thread(self._save_user, user_id, username, first_name)

    async def create_ad(self, user_id: int, fields: dict, auto_approve: bool = False) -> int:
        """Создаёт объявление и возвращает его номер. При превышении лимита: LimitReached."""
        return await asyncio.to_thread(self._create_ad, user_id, fields, auto_approve)

    async def get_ad(self, ad_id: int) -> dict | None:
        """Объявление с данными автора или None."""
        return await asyncio.to_thread(self._get_ad, ad_id)

    async def set_status(self, ad_id: int, status: str, owner_id: int | None = None) -> bool:
        """Меняет статус. Если задан owner_id, меняет только объявление этого автора."""
        return await asyncio.to_thread(self._set_status, ad_id, status, owner_id)

    async def set_hidden(self, ad_id: int, owner_id: int, hidden: bool) -> dict | None:
        """Автор скрывает (hidden=True) или показывает своё объявление.

        Возвращает объявление после попытки или None, если оно не найдено или чужое.
        Если статус не подходит (например, показать отклонённое), объявление не меняется.
        При возврате в каталог проверяется лимит: LimitReached.
        """
        return await asyncio.to_thread(self._set_hidden, ad_id, owner_id, hidden)

    async def search(
        self, category: str | None = None, query: str | None = None, page: int = 0
    ) -> tuple[list[dict], int]:
        """Опубликованные объявления на странице (с нуля) и общее их число.

        Без category ищет по всем категориям, query ищет в названии и описании без учёта регистра.
        """
        return await asyncio.to_thread(self._search, category, query, page)

    async def list_by_user(self, user_id: int) -> list[dict]:
        """Все объявления одного автора, новые первыми."""
        return await asyncio.to_thread(self._list_by_user, user_id)

    async def list_pending(self) -> list[dict]:
        """Очередь на проверке, старые первыми."""
        return await asyncio.to_thread(self._list_pending)

    async def delete_ad(self, ad_id: int, owner_id: int | None = None) -> bool:
        """Удаляет объявление. Если задан owner_id, только если оно принадлежит автору."""
        return await asyncio.to_thread(self._delete_ad, ad_id, owner_id)

    async def add_report(self, user_id: int, ad_id: int) -> bool:
        """Записывает жалобу. True, если человек жалуется на это объявление впервые."""
        return await asyncio.to_thread(self._add_report, user_id, ad_id)

    async def stats(self) -> dict:
        """Число пользователей и объявлений по статусам."""
        return await asyncio.to_thread(self._stats)
