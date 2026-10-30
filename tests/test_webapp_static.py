"""Проверки страницы Mini App по файлам: безопасность, доступность, соответствие серверу."""

import re
import unittest
from pathlib import Path

from bot.categories import CATEGORIES
from bot.validators import (
    DESCRIPTION_LIMIT,
    LOCATION_LIMIT,
    PRICE_LIMIT,
    TITLE_LIMIT,
)
from webapp.api import MAX_QUERY_LENGTH
from webapp.main import CONTENT_SECURITY_POLICY

STATIC = Path(__file__).resolve().parent.parent / "webapp" / "static"
JS_FILES = sorted((STATIC / "js").glob("*.js"))
CSS_FILES = sorted((STATIC / "css").glob("*.css"))
HTML_FILE = STATIC / "index.html"

MIN_BODY_FONT_PX = 19
MIN_CAPTION_FONT_PX = 17
MIN_CONTROL_HEIGHT_PX = 56
MIN_TEXT_CONTRAST = 4.5
MIN_UI_CONTRAST = 3.0


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def css_variables() -> dict[str, str]:
    """Значения переменных из variables.css; ссылки вида var(--x) раскрываются."""
    variables = dict(re.findall(r"(--[\w-]+):\s*([^;]+?);", read(STATIC / "css" / "variables.css")))
    for name, value in variables.items():
        reference = re.fullmatch(r"var\((--[\w-]+)\)", value)
        if reference:
            variables[name] = variables[reference.group(1)]
    return variables


def pixels(value: str) -> int:
    return int(re.match(r"(\d+)px", value).group(1))


def luminance(color: str) -> float:
    channels = [int(color.lstrip("#")[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    linear = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast(first: str, second: str) -> float:
    lighter, darker = sorted((luminance(first), luminance(second)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


class AccessibilityTests(unittest.TestCase):
    def setUp(self):
        self.vars = css_variables()

    def test_font_and_control_sizes(self):
        self.assertGreaterEqual(pixels(self.vars["--font-size-body"]), MIN_BODY_FONT_PX)
        self.assertGreaterEqual(pixels(self.vars["--font-size-caption"]), MIN_CAPTION_FONT_PX)
        self.assertGreaterEqual(pixels(self.vars["--control-height"]), MIN_CONTROL_HEIGHT_PX)
        self.assertGreaterEqual(pixels(self.vars["--tabbar-height"]), MIN_CONTROL_HEIGHT_PX)

    def test_text_contrast_is_at_least_4_5(self):
        v = self.vars
        pairs = {
            "текст на фоне": ("--color-text", "--color-bg"),
            "текст на карточке": ("--color-text", "--color-surface"),
            "второстепенный на фоне": ("--color-text-muted", "--color-bg"),
            "второстепенный на карточке": ("--color-text-muted", "--color-surface"),
            "акцент на фоне": ("--color-accent", "--color-bg"),
            "акцент на карточке": ("--color-accent", "--color-surface"),
            "текст на акценте": ("--color-on-accent", "--color-accent"),
            "ошибка на фоне": ("--color-danger", "--color-bg"),
            "ошибка на карточке": ("--color-danger", "--color-surface"),
        }
        for name, (foreground, background) in pairs.items():
            with self.subTest(pair=name):
                self.assertGreaterEqual(contrast(v[foreground], v[background]), MIN_TEXT_CONTRAST)

    def test_input_border_is_visible(self):
        ratio = contrast(self.vars["--color-field-border"], self.vars["--color-bg"])
        self.assertGreaterEqual(ratio, MIN_UI_CONTRAST)

    def test_palette_matches_the_design(self):
        expected = {
            "--color-bg": "#0e2a20",
            "--color-surface": "#15382b",
            "--color-border": "#2f5e4a",
            "--color-text": "#f6f1e3",
            "--color-text-muted": "#c5d3c8",
            "--color-accent": "#e2be6a",
            "--color-on-accent": "#0e2a20",
        }
        for name, color in expected.items():
            self.assertEqual(self.vars[name].lower(), color, name)

    def test_other_css_files_use_only_variables(self):
        for path in CSS_FILES:
            if path.name == "variables.css":
                continue
            css = read(path)
            with self.subTest(file=path.name):
                self.assertEqual(
                    re.findall(r"#[0-9a-fA-F]{3,8}\b", css), [], "цвет не из переменной"
                )
                self.assertEqual(
                    re.findall(r"font-size:\s*\d", css), [], "размер шрифта не из переменной"
                )

    def test_buttons_and_fields_use_control_height(self):
        components = read(STATIC / "css" / "components.css")
        for selector in (".button", ".input", ".choice"):
            block = re.search(re.escape(selector) + r" \{([^}]*)\}", components).group(1)
            with self.subTest(selector=selector):
                self.assertIn("min-height: var(--control-height)", block)

    def test_font_is_manrope(self):
        self.assertIn("Manrope", self.vars["--font-family"])
        self.assertIn("family=Manrope", read(HTML_FILE))


class SafetyTests(unittest.TestCase):
    def test_scripts_never_write_html(self):
        forbidden = [
            "innerHTML",
            "outerHTML",
            "insertAdjacentHTML",
            "document.write",
            "eval(",
            "new Function",
        ]
        for path in JS_FILES:
            code = read(path)
            for word in forbidden:
                with self.subTest(file=path.name, word=word):
                    self.assertNotIn(word, code)

    def test_no_global_variables(self):
        for path in JS_FILES:
            code = read(path)
            with self.subTest(file=path.name):
                self.assertEqual(re.findall(r"^var\s", code, re.MULTILINE), [])
                self.assertEqual(re.findall(r"\bwindow\.\w+\s*=[^=]", code), [], "запись в window")

    def test_page_has_no_inline_scripts_styles_or_handlers(self):
        html = read(HTML_FILE)
        self.assertEqual(re.findall(r"<script(?![^>]*\bsrc=)[^>]*>", html), [])
        self.assertEqual(re.findall(r"\sstyle=", html), [])
        self.assertEqual(re.findall(r"\son\w+=", html), [])
        self.assertEqual(re.findall(r"<style", html), [])

    def test_external_hosts_are_allowed_by_content_security_policy(self):
        hosts = set(re.findall(r"https://([\w.-]+)", read(HTML_FILE)))
        for host in hosts:
            with self.subTest(host=host):
                self.assertIn(host, CONTENT_SECURITY_POLICY)

    def test_no_emoji_anywhere_in_the_page(self):
        emoji = re.compile("[\U0001f000-\U0001faff☀-➿️⭐⬆]")
        for path in [HTML_FILE, *JS_FILES, *CSS_FILES]:
            with self.subTest(file=path.name):
                self.assertEqual(emoji.findall(read(path)), [])

    def test_all_script_imports_exist_and_are_used(self):
        imported = set()
        for path in JS_FILES:
            for name in re.findall(r"from '\./([\w-]+\.js)'", read(path)):
                imported.add(name)
                self.assertTrue((STATIC / "js" / name).exists(), f"{path.name}: нет {name}")
        entry = "app.js"
        for path in JS_FILES:
            if path.name != entry:
                self.assertIn(path.name, imported, f"{path.name} нигде не подключён")


class ServerParityTests(unittest.TestCase):
    """Числа в скриптах должны совпадать с серверными правилами."""

    def test_field_limits_match_validators(self):
        wizard = read(STATIC / "js" / "wizard.js")
        found = {
            key: (int(low), int(high))
            for key, low, high in re.findall(r"(\w+): \{ min: (\d+), max: (\d+) \}", wizard)
        }
        expected = {
            "title": TITLE_LIMIT,
            "description": DESCRIPTION_LIMIT,
            "price": PRICE_LIMIT,
            "location": LOCATION_LIMIT,
        }
        for key, limit in expected.items():
            with self.subTest(field=key):
                self.assertEqual(found[key], (limit.min, limit.max))

    def test_search_length_matches_api(self):
        screens = read(STATIC / "js" / "screens.js")
        value = int(re.search(r"SEARCH_MAX_LENGTH = (\d+)", screens).group(1))
        self.assertEqual(value, MAX_QUERY_LENGTH)

    def test_every_category_has_an_icon(self):
        icons = read(STATIC / "js" / "icons.js")
        defined = set(re.findall(r"^  (\w+): \[", icons, re.MULTILINE))
        for category in CATEGORIES:
            with self.subTest(category=category.key):
                self.assertIn(category.key, defined)

    def test_description_limit_is_300_as_in_the_design(self):
        self.assertEqual(DESCRIPTION_LIMIT.max, 300)

    def test_page_has_four_tabs_in_the_required_order(self):
        app = read(STATIC / "js" / "app.js")
        tabs_block = re.search(r"const TABS = \[(.*?)\n\];", app, re.DOTALL).group(1)
        labels = re.findall(r"label: '([^']+)'", tabs_block)
        self.assertEqual(labels, ["Каталог", "Разместить", "Мои", "Помощь"])


if __name__ == "__main__":
    unittest.main()
