"""Тесты внешнего вида: короткая карточка, кнопки по одной в ряд, порядок обработчиков."""

import unittest

from aiogram.types import InlineKeyboardMarkup, User

from bot import keyboards, texts
from bot.handlers import ROUTERS, admin, menu
from bot.validators import DESCRIPTION_LIMIT, PRICE_LIMIT, TITLE_LIMIT

MAX_CARD_LINES = 6


def make_ad(**changes) -> dict:
    """Объявление с самыми длинными допустимыми полями, чтобы проверять худший случай."""
    ad = {
        "id": 12,
        "user_id": 7,
        "category": "it",
        "title": "Т" * TITLE_LIMIT.max,
        "description": "О" * DESCRIPTION_LIMIT.max,
        "price": "Ц" * PRICE_LIMIT.max,
        "location": "Минск",
        "phone": "+375 29 123-45-67",
        "status": "active",
        "author_name": "Анна",
        "author_username": "anna",
    }
    return {**ad, **changes}


def all_buttons(markup: InlineKeyboardMarkup):
    return [button for row in markup.inline_keyboard for button in row]


class CardTests(unittest.TestCase):
    def test_card_has_at_most_six_lines_in_worst_case(self):
        self.assertLessEqual(len(texts.ad_card(make_ad()).split("\n")), MAX_CARD_LINES)

    def test_card_without_empty_lines(self):
        self.assertNotIn("", texts.ad_card(make_ad()).split("\n"))

    def test_first_line_has_bold_title_and_price(self):
        first = texts.ad_card(make_ad(title="Сайты", price="от 300 BYN")).split("\n")[0]
        self.assertEqual(first, "<b>Сайты</b> · 💰 от 300 BYN")

    def test_card_without_phone_is_shorter(self):
        with_phone = texts.ad_card(make_ad()).split("\n")
        without_phone = texts.ad_card(make_ad(phone=None)).split("\n")
        self.assertEqual(len(with_phone) - len(without_phone), 1)

    def test_review_stays_short(self):
        review = texts.ad_for_review(make_ad()).split("\n")
        self.assertLessEqual(len(review), MAX_CARD_LINES + 1)  # плюс заголовок для администратора

    def test_user_text_is_escaped(self):
        card = texts.ad_card(make_ad(title="<b>x</b>", author_name="<i>y</i>", description="a&b"))
        self.assertNotIn("<i>", card)
        self.assertIn("&lt;b&gt;x&lt;/b&gt;", card)
        self.assertIn("a&amp;b", card)


class ButtonTests(unittest.TestCase):
    def test_moderation_buttons_are_one_per_row(self):
        for row in keyboards.moderation(5).inline_keyboard:
            self.assertEqual(len(row), 1, [button.text for button in row])

    def test_app_is_opened_by_inline_web_app_button(self):
        # Из кнопки нижней клавиатуры Telegram не передаёт подпись, вход не получился бы
        markup = keyboards.open_app("https://example.org")
        self.assertEqual([len(row) for row in markup.inline_keyboard], [1])
        button = all_buttons(markup)[0]
        self.assertEqual(button.text, texts.BTN_OPEN_APP)
        self.assertEqual(button.web_app.url, "https://example.org")


class RouterOrderTests(unittest.TestCase):
    def test_menu_catch_all_is_last_so_admin_commands_still_work(self):
        self.assertEqual(ROUTERS[-1], menu.router)
        self.assertLess(ROUTERS.index(admin.router), ROUTERS.index(menu.router))


class AdminTextTests(unittest.TestCase):
    def test_report_for_admin_is_short_and_escaped(self):
        reporter = User(id=5, is_bot=False, first_name="<b>Гость</b>", username="guest")
        lines = texts.report_for_admin(make_ad(), reporter).split("\n")
        self.assertNotIn("", lines)
        self.assertLessEqual(len(lines), MAX_CARD_LINES + 3)  # карточка и три строки администратору
        self.assertIn("&lt;b&gt;Гость&lt;/b&gt;", lines[1])
        self.assertIn("/delete 12", lines[-1])

    def test_admin_stats_has_no_empty_lines(self):
        stats = {"users": 3, "ads": {"pending": 1, "active": 2, "rejected": 0, "hidden": 0}}
        self.assertNotIn("", texts.admin_stats(stats).split("\n"))

    def test_moderation_texts_escape_title(self):
        ad = make_ad(title="<i>x</i>")
        self.assertNotIn("<i>", texts.moderation_notice(ad, approved=True))
        self.assertNotIn("<i>", texts.moderation_result(ad, True, "<b>Босс</b>"))


if __name__ == "__main__":
    unittest.main()
