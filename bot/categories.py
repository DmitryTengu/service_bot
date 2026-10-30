"""Категории услуг. Чтобы изменить список, правьте CATEGORIES ниже.

Каждая категория: значок, ключ (латиница, без пробелов, не менять после запуска,
иначе старые объявления потеряют категорию) и название, которое видят пользователи.
"""

from typing import NamedTuple


class Category(NamedTuple):
    icon: str
    key: str
    title: str

    @property
    def label(self) -> str:
        """Название со значком для кнопок."""
        return f"{self.icon} {self.title}"


CATEGORIES = [
    Category("🔧", "repair", "Ремонт и мастера"),
    Category("💅", "beauty", "Красота"),
    Category("📚", "education", "Обучение и репетиторы"),
    Category("🧸", "kids", "Дети и няни"),
    Category("🍽", "food", "Еда и кейтеринг"),
    Category("⚖️", "legal", "Юристы и бухгалтеры"),
    Category("🌐", "translate", "Переводы"),
    Category("📷", "media", "Фото и видео"),
    Category("🎉", "events", "Праздники и мероприятия"),
    Category("🚚", "transport", "Транспорт и доставка"),
    Category("💻", "it", "IT и сайты"),
    Category("📦", "other", "Другое"),
]

_BY_KEY = {category.key: category for category in CATEGORIES}


def get_category(key: str) -> Category | None:
    """Находит категорию по ключу, если такой нет, возвращает None."""
    return _BY_KEY.get(key)


def category_label(key: str) -> str:
    """Название категории со значком; для неизвестного ключа возвращает сам ключ."""
    category = get_category(key)
    return category.label if category else key
