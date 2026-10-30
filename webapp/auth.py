"""Проверка пользователя Mini App: подпись initData, членство и лимит запросов.

Telegram передаёт приложению строку initData, подписанную токеном бота. Подделать её без
токена нельзя, поэтому номер пользователя берём только из неё и больше ниоткуда.
"""

import hashlib
import hmac
import json
import time
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import parse_qsl

# Сколько времени initData считается свежей (защита от использования украденной строки)
MAX_AUTH_AGE_SECONDS = 24 * 60 * 60
# Допустимое расхождение часов, если auth_date оказался чуть «из будущего»
CLOCK_SKEW_SECONDS = 60
# Настоящая initData занимает пару килобайт; всё больше отбрасываем, не разбирая
MAX_INIT_DATA_LENGTH = 4096

REQUESTS_PER_MINUTE = 30
RATE_WINDOW_SECONDS = 60

_SECRET_KEY_LABEL = b"WebAppData"


class AuthError(Exception):
    """initData не прошла проверку. Подробности наружу не отдаём, только в тестах и логах."""


@dataclass(frozen=True)
class TelegramUser:
    id: int
    first_name: str
    username: str | None


def _sign(data_check_string: str, bot_token: str) -> str:
    """Подпись по правилам Telegram: ключ = HMAC_SHA256("WebAppData", токен бота)."""
    secret_key = hmac.new(_SECRET_KEY_LABEL, bot_token.encode(), hashlib.sha256).digest()
    return hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()


def _parse_fields(init_data: str) -> dict[str, str]:
    if not init_data or len(init_data) > MAX_INIT_DATA_LENGTH:
        raise AuthError("пустая или слишком длинная строка")
    fields = dict(parse_qsl(init_data, keep_blank_values=True))
    if "hash" not in fields:
        raise AuthError("нет подписи")
    return fields


def _check_signature(fields: dict[str, str], bot_token: str) -> None:
    received_hash = fields.pop("hash")
    data_check_string = "\n".join(f"{key}={fields[key]}" for key in sorted(fields))
    expected_hash = _sign(data_check_string, bot_token)
    # compare_digest сравнивает за одинаковое время, так подпись нельзя подобрать по замеру
    if not hmac.compare_digest(expected_hash.encode(), received_hash.encode()):
        raise AuthError("подпись не совпала")


def _check_freshness(fields: dict[str, str], now: float) -> None:
    try:
        auth_date = int(fields["auth_date"])
    except (KeyError, ValueError):
        raise AuthError("нет даты авторизации") from None
    if now - auth_date > MAX_AUTH_AGE_SECONDS:
        raise AuthError("данные просрочены")
    if auth_date - now > CLOCK_SKEW_SECONDS:
        raise AuthError("дата из будущего")


def _read_user(fields: dict[str, str]) -> TelegramUser:
    try:
        raw = json.loads(fields["user"])
        user_id = raw["id"]
        first_name = raw.get("first_name", "")
        username = raw.get("username")
    except (KeyError, ValueError, TypeError, AttributeError):
        raise AuthError("нет данных пользователя") from None
    # bool в Python тоже int, поэтому отдельно исключаем True и False
    if not isinstance(user_id, int) or isinstance(user_id, bool) or user_id <= 0:
        raise AuthError("неверный номер пользователя")
    return TelegramUser(id=user_id, first_name=str(first_name), username=username or None)


def validate_init_data(init_data: str, bot_token: str, now: float | None = None) -> TelegramUser:
    """Проверяет initData и возвращает пользователя из неё; при любой проблеме: AuthError."""
    fields = _parse_fields(init_data)
    _check_signature(fields, bot_token)
    _check_freshness(fields, time.time() if now is None else now)
    return _read_user(fields)


async def is_member(user_id: int) -> bool:
    """Можно ли этому человеку пользоваться приложением.

    Единственное место проверки доступа. Сейчас открыто для всех; позже здесь подключим
    закрытый доступ по коду приглашения, остальной код менять не придётся.
    """
    return True


class RateLimiter:
    """Не больше limit запросов за window секунд на человека; счётчики только в памяти."""

    def __init__(
        self,
        limit: int = REQUESTS_PER_MINUTE,
        window: float = RATE_WINDOW_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._limit = limit
        self._window = window
        self._clock = clock
        self._hits: dict[int, deque[float]] = defaultdict(deque)

    def allow(self, user_id: int) -> bool:
        """Учитывает запрос и говорит, можно ли его выполнить."""
        now = self._clock()
        hits = self._hits[user_id]
        while hits and now - hits[0] >= self._window:
            hits.popleft()
        if len(hits) >= self._limit:
            return False
        hits.append(now)
        return True
