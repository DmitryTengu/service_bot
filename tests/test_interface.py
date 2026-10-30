"""Тесты внешнего вида: короткая карточка, длина подписей кнопок, кнопки по одной в ряд."""

import unittest

from aiogram.types import InlineKeyboardMarkup, User

from bot import keyboards, texts
from bot.config import PAGE_SIZE
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

    def test_my_ad_card_and_review_stay_short(self):
        self.assertLessEqual(len(texts.my_ad_card(make_ad()).split("\n")), MAX_CARD_LINES)
        review = texts.ad_for_review(make_ad()).split("\n")
        self.assertLessEqual(len(review), MAX_CARD_LINES + 1)  # плюс заголовок для администратора

    def test_user_text_is_escaped(self):
        card = texts.ad_card(make_ad(title="<b>x</b>", author_name="<i>y</i>", description="a&b"))
        self.assertNotIn("<i>", card)
        self.assertIn("&lt;b&gt;x&lt;/b&gt;", card)
        self.assertIn("a&amp;b", card)


class ButtonTests(unittest.TestCase):
    def assert_short_labels(self, markup: InlineKeyboardMarkup):
        for button in all_buttons(markup):
            self.assertLessEqual(len(button.text), texts.BUTTON_TEXT_LIMIT, button.text)

    def assert_one_per_row(self, markup: InlineKeyboardMarkup):
        for row in markup.inline_keyboard:
            self.assertEqual(len(row), 1, [button.text for button in row])

    def test_categories_are_one_per_row_and_short(self):
        for markup in (keyboards.categories_menu(), keyboards.post_categories()):
            self.assert_one_per_row(markup)
            self.assert_short_labels(markup)

    def test_ads_page_buttons_are_one_per_row_and_short(self):
        ads = [make_ad(id=number) for number in range(PAGE_SIZE)]
        middle_page = keyboards.ads_page(ads, "it", page=1, total=PAGE_SIZE * 3)
        self.assert_one_per_row(middle_page)
        self.assert_short_labels(middle_page)
        # Все объявления плюс «Предыдущие», «Следующие» и «К категориям»
        self.assertEqual(len(all_buttons(middle_page)), PAGE_SIZE + 3)

    def test_first_and_last_page_have_only_one_direction(self):
        ads = [make_ad()]
        first = [b.text for b in all_buttons(keyboards.ads_page(ads, "it", 0, PAGE_SIZE * 2))]
        last = [b.text for b in all_buttons(keyboards.ads_page(ads, "it", 1, PAGE_SIZE * 2))]
        self.assertIn(texts.BTN_NEXT_PAGE, first)
        self.assertNotIn(texts.BTN_PREV_PAGE, first)
        self.assertIn(texts.BTN_PREV_PAGE, last)
        self.assertNotIn(texts.BTN_NEXT_PAGE, last)

    def test_ad_card_buttons_are_one_per_row(self):
        markup = keyboards.ad_card(make_ad(), page=0)
        self.assert_one_per_row(markup)
        self.assert_short_labels(markup)

    def test_my_ads_screens_are_one_per_row_and_short(self):
        for status in ("pending", "active", "hidden", "rejected"):
            ad = make_ad(status=status)
            for markup in (keyboards.my_ad_actions(ad), keyboards.confirm_delete(ad["id"])):
                self.assert_one_per_row(markup)
                self.assert_short_labels(markup)
        listing = keyboards.my_ads_list([make_ad(id=number) for number in range(3)])
        self.assert_one_per_row(listing)
        self.assert_short_labels(listing)

    def test_hide_and_show_depend_on_status(self):
        def labels(status):
            return [b.text for b in all_buttons(keyboards.my_ad_actions(make_ad(status=status)))]

        self.assertIn(texts.BTN_HIDE, labels("active"))
        self.assertNotIn(texts.BTN_SHOW, labels("active"))
        self.assertIn(texts.BTN_SHOW, labels("hidden"))
        self.assertNotIn(texts.BTN_HIDE, labels("hidden"))
        for status in ("pending", "rejected"):
            self.assertNotIn(texts.BTN_HIDE, labels(status))
            self.assertNotIn(texts.BTN_SHOW, labels(status))

    def test_moderation_buttons_are_one_per_row(self):
        self.assert_one_per_row(keyboards.moderation(5))

    def test_main_menu_is_persistent_with_one_button_per_row(self):
        menu = keyboards.main_menu()
        self.assertTrue(menu.is_persistent)
        self.assertEqual([len(row) for row in menu.keyboard], [1, 1, 1, 1])


class AppButtonTests(unittest.TestCase):
    @staticmethod
    def labels(menu) -> list[str]:
        return [row[0].text for row in menu.keyboard]

    def test_menu_has_app_button_only_when_enabled(self):
        self.assertNotIn(texts.BTN_OPEN_APP, self.labels(keyboards.main_menu()))
        with_app = keyboards.main_menu(app_enabled=True)
        self.assertEqual(self.labels(with_app)[0], texts.BTN_OPEN_APP)
        self.assertEqual(len(with_app.keyboard), 5)
        self.assertTrue(with_app.is_persistent)
        self.assertEqual([len(row) for row in with_app.keyboard], [1] * 5)

    def test_app_is_opened_by_inline_button_not_keyboard_button(self):
        # Из кнопки нижней клавиатуры Telegram не передаёт подпись, вход не получился бы
        for row in keyboards.main_menu(app_enabled=True).keyboard:
            self.assertIsNone(row[0].web_app)
        markup = keyboards.open_app("https://example.org")
        self.assertEqual([len(row) for row in markup.inline_keyboard], [1])
        self.assertEqual(markup.inline_keyboard[0][0].web_app.url, "https://example.org")


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


class ShortenTests(unittest.TestCase):
    def test_short_text_is_unchanged(self):
        self.assertEqual(texts.shorten("Сайты"), "Сайты")

    def test_long_text_is_cut_to_limit_with_ellipsis(self):
        result = texts.shorten("а" * 100)
        self.assertEqual(len(result), texts.BUTTON_TEXT_LIMIT)
        self.assertTrue(result.endswith("…"))


if __name__ == "__main__":
    unittest.main()
