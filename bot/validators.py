"""Проверка того, что вводит пользователь при размещении объявления.

Каждая функция возвращает очищенное значение или бросает ValidationError
с понятным человеку объяснением.
"""

import re
from typing import NamedTuple


class ValidationError(ValueError):
    """Ввод не подошёл; текст ошибки можно показывать пользователю."""


class Limit(NamedTuple):
    min: int
    max: int


TITLE_LIMIT = Limit(3, 80)
# 300 символов одним абзацем: так карточка объявления остаётся короткой
DESCRIPTION_LIMIT = Limit(10, 300)
PRICE_LIMIT = Limit(1, 40)
LOCATION_LIMIT = Limit(2, 60)
# Для телефона считаем только цифры, а не весь текст
PHONE_DIGITS_LIMIT = Limit(7, 15)

# Телефон начинается с цифры или плюса, дальше допустимы пробелы, дефисы и скобки
_PHONE_PATTERN = re.compile(r"^[+\d][\d\s\-()]*$")


def _one_line(text: str) -> str:
    """Убирает лишние пробелы и переносы строк."""
    return " ".join(text.split())


def _check_length(value: str, limit: Limit, field: str) -> str:
    if not value:
        raise ValidationError(f"{field}: пустое значение не подходит.")
    if not limit.min <= len(value) <= limit.max:
        raise ValidationError(
            f"{field}: нужно от {limit.min} до {limit.max} символов, сейчас {len(value)}."
        )
    return value


def validate_title(text: str) -> str:
    """Название услуги."""
    return _check_length(_one_line(text), TITLE_LIMIT, "Название")


def validate_description(text: str) -> str:
    """Описание одним абзацем: переносы строк заменяются пробелами."""
    return _check_length(_one_line(text), DESCRIPTION_LIMIT, "Описание")


def validate_price(text: str) -> str:
    """Цена текстом: «от 20 BYN», «договорная» и так далее."""
    return _check_length(_one_line(text), PRICE_LIMIT, "Цена")


def validate_location(text: str) -> str:
    """Район или город."""
    return _check_length(_one_line(text), LOCATION_LIMIT, "Район или город")


def validate_phone(text: str) -> str:
    """Телефон: допускаем +, цифры, пробелы, дефисы и скобки."""
    phone = _one_line(text)
    digits = sum(char.isdigit() for char in phone)
    if not _PHONE_PATTERN.match(phone) or not (
        PHONE_DIGITS_LIMIT.min <= digits <= PHONE_DIGITS_LIMIT.max
    ):
        raise ValidationError(
            f"Телефон: от {PHONE_DIGITS_LIMIT.min} до {PHONE_DIGITS_LIMIT.max} цифр, "
            "можно с +, пробелами, скобками и дефисом."
        )
    return phone
