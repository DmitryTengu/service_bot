"""Тесты проверки ввода."""

import unittest

from bot.validators import (
    DESCRIPTION_LIMIT,
    LOCATION_LIMIT,
    PRICE_LIMIT,
    TITLE_LIMIT,
    ValidationError,
    validate_description,
    validate_location,
    validate_phone,
    validate_price,
    validate_title,
)

# Поля с ограничением длины: (функция проверки, ограничение)
LENGTH_CHECKED = [
    (validate_title, TITLE_LIMIT),
    (validate_description, DESCRIPTION_LIMIT),
    (validate_price, PRICE_LIMIT),
    (validate_location, LOCATION_LIMIT),
]


class LengthTests(unittest.TestCase):
    def test_empty_and_blank_values_are_rejected(self):
        for validate, _ in LENGTH_CHECKED:
            for text in ("", "   ", "\n\t "):
                name = validate.__name__
                with (
                    self.subTest(validate=name, text=text),
                    self.assertRaisesRegex(ValidationError, "пустое"),
                ):
                    validate(text)

    def test_too_short_and_too_long_are_rejected_with_explanation(self):
        for validate, limit in LENGTH_CHECKED:
            for length in (limit.min - 1, limit.max + 1):
                if length == 0:
                    continue  # пустой ввод проверяется отдельным тестом
                name, expected = validate.__name__, f"{limit.min} до {limit.max}"
                with (
                    self.subTest(validate=name, length=length),
                    self.assertRaisesRegex(ValidationError, expected),
                ):
                    validate("а" * length)

    def test_boundary_lengths_are_accepted(self):
        for validate, limit in LENGTH_CHECKED:
            for length in (limit.min, limit.max):
                with self.subTest(validate=validate.__name__, length=length):
                    self.assertEqual(validate("а" * length), "а" * length)

    def test_error_names_the_field(self):
        with self.assertRaisesRegex(ValidationError, "^Название"):
            validate_title("a")
        with self.assertRaisesRegex(ValidationError, "^Описание"):
            validate_description("коротко")


class CleaningTests(unittest.TestCase):
    def test_single_line_fields_collapse_whitespace(self):
        self.assertEqual(validate_title("  Ремонт \n  ноутбуков  "), "Ремонт ноутбуков")
        self.assertEqual(validate_price("от   20\tBYN"), "от 20 BYN")
        self.assertEqual(validate_location(" Минск,  Уручье "), "Минск, Уручье")

    def test_description_becomes_one_paragraph(self):
        text = validate_description("  Первая строка\n\nВторая строка  ")
        self.assertEqual(text, "Первая строка Вторая строка")

    def test_length_is_counted_after_cleaning(self):
        # Пробелы по краям не должны спасать слишком короткое название
        with self.assertRaises(ValidationError):
            validate_title("  ab  ")


class PhoneTests(unittest.TestCase):
    def test_valid_phones(self):
        for text in ("+375291234567", "+375 29 123-45-67", "8 (017) 123-45-67", "1234567"):
            with self.subTest(text=text):
                self.assertEqual(validate_phone(text), text)

    def test_phone_whitespace_is_cleaned(self):
        self.assertEqual(validate_phone("  +375  29 1234567 "), "+375 29 1234567")

    def test_invalid_phones(self):
        for text in (
            "abc",
            "12345",
            "+375 29 abc 45",
            "1234567890123456",
            "",
            "  ",
            "29-+-1234567",
        ):
            with self.subTest(text=text), self.assertRaises(ValidationError):
                validate_phone(text)


if __name__ == "__main__":
    unittest.main()
