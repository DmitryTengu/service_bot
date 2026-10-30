"""Формы данных API: что приходит от страницы и что отправляется ей.

Правила для текста берутся из bot/validators.py, чтобы бот и приложение проверяли одинаково.
"""

from pydantic import BaseModel, ConfigDict, Field, field_validator

from bot.categories import get_category
from bot.validators import (
    validate_description,
    validate_location,
    validate_price,
    validate_title,
)

# Грубый потолок длины до точной проверки: огромный текст отбрасывается, не разбираясь
MAX_RAW_TEXT_LENGTH = 2000
MAX_CATEGORY_KEY_LENGTH = 40

_TEXT_CLEANERS = {
    "title": validate_title,
    "description": validate_description,
    "price": validate_price,
    "location": validate_location,
}


class ListingIn(BaseModel):
    """Новое объявление. Лишние поля (статус, номер автора) запрещены: их задаёт только сервер."""

    model_config = ConfigDict(extra="forbid")

    category: str = Field(max_length=MAX_CATEGORY_KEY_LENGTH)
    title: str = Field(max_length=MAX_RAW_TEXT_LENGTH)
    description: str = Field(max_length=MAX_RAW_TEXT_LENGTH)
    price: str = Field(max_length=MAX_RAW_TEXT_LENGTH)
    location: str = Field(max_length=MAX_RAW_TEXT_LENGTH)

    @field_validator("category")
    @classmethod
    def category_exists(cls, key: str) -> str:
        if get_category(key) is None:
            raise ValueError("Такой категории нет.")
        return key

    @field_validator("title", "description", "price", "location")
    @classmethod
    def clean_text(cls, value: str, info) -> str:
        return _TEXT_CLEANERS[info.field_name](value)


class CategoryOut(BaseModel):
    """Категория без значка-эмодзи: значок страница выбирает сама по ключу."""

    key: str
    title: str


class ListingOut(BaseModel):
    """Публичная карточка. Номера автора здесь нет: контакт отдаётся готовой ссылкой."""

    id: int
    category: str
    category_title: str
    title: str
    description: str
    price: str
    location: str
    phone: str | None
    author_name: str
    author_username: str | None
    contact_url: str | None


class MyListingOut(ListingOut):
    """Своё объявление: дополнительно виден статус."""

    status: str


class ListingsPage(BaseModel):
    items: list[ListingOut]
    total: int
    page: int
    pages: int


class CreatedOut(BaseModel):
    id: int
    status: str
