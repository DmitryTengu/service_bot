"""Тесты API Mini App: подпись, права, создание, лимит, жалобы."""

import asyncio
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from bot.categories import CATEGORIES
from bot.config import MAX_LIVE_ADS, Settings
from bot.db import ACTIVE, HIDDEN, PENDING, Database
from tests.test_auth import BOT_TOKEN, make_init_data
from webapp.api import AppContext
from webapp.auth import MAX_AUTH_AGE_SECONDS, RateLimiter
from webapp.main import create_app

ADMIN_ID = 99
AUTHOR = 1
OTHER = 2
NEW_AD = {
    "category": "it",
    "title": "Сайты",
    "description": "Делаю сайты под ключ",
    "price": "от 300 BYN",
    "location": "Минск",
}


class FakeBot:
    """Вместо настоящего бота: запоминает, что и кому отправили."""

    def __init__(self):
        self.sent = []
        self.session = SimpleNamespace(close=self._close)

    async def send_message(self, chat_id, text, reply_markup=None, **kwargs):
        self.sent.append(SimpleNamespace(chat_id=chat_id, text=text, markup=reply_markup))

    async def _close(self):
        pass


def headers_for(user_id: int, token: str = BOT_TOKEN, age: int = 0) -> dict[str, str]:
    user = {"id": user_id, "first_name": f"Имя{user_id}", "username": f"user{user_id:04d}"}
    init_data = make_init_data(user=user, auth_date=int(time.time()) - age, token=token)
    return {"Authorization": f"tma {init_data}"}


class ApiTestCase(unittest.TestCase):
    def setUp(self):
        self._folder = tempfile.TemporaryDirectory()
        self.addCleanup(self._folder.cleanup)
        self.make_client()

    def make_client(self, auto_approve: bool = False, rate_limit: int = 1000) -> None:
        settings = Settings(
            bot_token=BOT_TOKEN,
            admin_ids=frozenset({ADMIN_ID}),
            db_path=Path(self._folder.name) / f"{time.monotonic_ns()}.db",
            auto_approve=auto_approve,
        )
        self.db = Database(settings.db_path)
        self.bot = FakeBot()
        context = AppContext(settings, self.db, self.bot, RateLimiter(limit=rate_limit))
        self.client = TestClient(create_app(context))
        self.client.__enter__()  # запускает создание таблиц
        self.addCleanup(self.client.__exit__, None, None, None)

    def add_ad(self, owner: int = AUTHOR, status: str = ACTIVE, **changes) -> int:
        """Создаёт объявление напрямую в базе, минуя API."""

        async def create() -> int:
            await self.db.save_user(owner, f"user{owner:04d}", f"Имя{owner}")
            ad_id = await self.db.create_ad(owner, {**NEW_AD, **changes}, auto_approve=True)
            if status != ACTIVE:
                await self.db.set_status(ad_id, status)
            return ad_id

        return asyncio.run(create())

    def status_of(self, ad_id: int) -> str | None:
        ad = asyncio.run(self.db.get_ad(ad_id))
        return ad["status"] if ad else None

    def get(self, url: str, user: int = AUTHOR, **kwargs):
        return self.client.get(url, headers=headers_for(user), **kwargs)

    def post(self, url: str, user: int = AUTHOR, json=None):
        return self.client.post(url, headers=headers_for(user), json=json)

    def delete(self, url: str, user: int = AUTHOR):
        return self.client.delete(url, headers=headers_for(user))


class AuthTests(ApiTestCase):
    def test_requests_without_valid_signature_are_rejected(self):
        bad_headers = {
            "no header": {},
            "wrong scheme": {"Authorization": "Bearer abc"},
            "garbage": {"Authorization": "tma not-a-signature"},
            "empty": {"Authorization": "tma "},
            "other token": headers_for(AUTHOR, token="999:OTHER"),
            "expired": headers_for(AUTHOR, age=MAX_AUTH_AGE_SECONDS + 10),
        }
        for name, headers in bad_headers.items():
            with self.subTest(case=name):
                self.assertEqual(self.client.get("/api/listings", headers=headers).status_code, 401)
                self.assertEqual(
                    self.client.get("/api/my/listings", headers=headers).status_code, 401
                )

    def test_rejection_reason_is_logged_without_secrets(self):
        headers = headers_for(AUTHOR, token="999:OTHER")
        with self.assertLogs("webapp.api", level="WARNING") as logs:
            self.assertEqual(self.client.get("/api/listings", headers=headers).status_code, 401)
        logged = "\n".join(logs.output)
        self.assertIn("подпись не совпала", logged)
        init_data = headers["Authorization"].removeprefix("tma ")
        for secret in (BOT_TOKEN, init_data, "hash="):
            self.assertNotIn(secret, logged)

    def test_every_method_except_categories_requires_user(self):
        ad_id = self.add_ad()
        calls = [
            ("get", "/api/listings"),
            ("get", f"/api/listings/{ad_id}"),
            ("post", "/api/listings"),
            ("get", "/api/my/listings"),
            ("post", f"/api/my/listings/{ad_id}/hide"),
            ("post", f"/api/my/listings/{ad_id}/show"),
            ("delete", f"/api/my/listings/{ad_id}"),
            ("post", f"/api/listings/{ad_id}/report"),
        ]
        for method, url in calls:
            with self.subTest(url=url, method=method):
                self.assertEqual(getattr(self.client, method)(url).status_code, 401)
        self.assertEqual(self.status_of(ad_id), ACTIVE)

    def test_user_id_in_body_or_query_is_ignored(self):
        ad_id = self.add_ad(owner=AUTHOR)
        # Чужой номер в адресе и теле ни на что не влияет: пользователь только из подписи
        response = self.client.delete(
            f"/api/my/listings/{ad_id}?user_id={AUTHOR}", headers=headers_for(OTHER)
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.status_of(ad_id), ACTIVE)

    def test_categories_are_public_and_have_no_emoji(self):
        response = self.client.get("/api/categories")
        self.assertEqual(response.status_code, 200)
        self.assertEqual([c["key"] for c in response.json()], [c.key for c in CATEGORIES])
        for category in CATEGORIES:
            self.assertNotIn(category.icon, response.text)

    def test_documentation_pages_are_disabled(self):
        for url in ("/docs", "/redoc", "/openapi.json"):
            self.assertEqual(self.client.get(url).status_code, 404)


class ReadTests(ApiTestCase):
    def test_lists_only_published_listings_without_author_id(self):
        published = self.add_ad(title="Опубликовано")
        self.add_ad(owner=OTHER, status=PENDING, title="На проверке")
        data = self.get("/api/listings").json()
        self.assertEqual([item["id"] for item in data["items"]], [published])
        self.assertEqual((data["total"], data["page"], data["pages"]), (1, 0, 1))
        self.assertNotIn("user_id", data["items"][0])
        self.assertNotIn("status", data["items"][0])

    def test_contact_url_only_for_authors_with_username(self):
        ad_id = self.add_ad()
        self.assertEqual(
            self.get(f"/api/listings/{ad_id}").json()["contact_url"], "https://t.me/user0001"
        )

        async def drop_username():
            await self.db.save_user(AUTHOR, None, "Имя1")

        asyncio.run(drop_username())
        self.assertIsNone(self.get(f"/api/listings/{ad_id}").json()["contact_url"])

    def test_search_by_text_and_category(self):
        self.add_ad(title="Ремонт ноутбуков")
        self.add_ad(owner=OTHER, category="beauty", title="Маникюр")
        titles = lambda url: sorted(i["title"] for i in self.get(url).json()["items"])
        self.assertEqual(titles("/api/listings?q=РЕМОНТ"), ["Ремонт ноутбуков"])
        self.assertEqual(titles("/api/listings?category=beauty"), ["Маникюр"])
        self.assertEqual(titles("/api/listings"), ["Маникюр", "Ремонт ноутбуков"])

    def test_bad_query_parameters_are_rejected(self):
        for url in (
            "/api/listings?category=nope",
            "/api/listings?page=-1",
            "/api/listings?page=abc",
            f"/api/listings?q={'а' * 61}",
            "/api/listings/0",
            "/api/listings/abc",
        ):
            with self.subTest(url=url):
                self.assertEqual(self.get(url).status_code, 422)

    def test_unpublished_or_unknown_listing_is_not_found(self):
        pending = self.add_ad(status=PENDING)
        for ad_id in (pending, 999):
            self.assertEqual(self.get(f"/api/listings/{ad_id}").status_code, 404)


class CreateTests(ApiTestCase):
    def test_new_listing_waits_for_review_and_admin_is_notified(self):
        response = self.post("/api/listings", json=NEW_AD)
        self.assertEqual(response.status_code, 201)
        ad_id = response.json()["id"]
        self.assertEqual(response.json()["status"], PENDING)
        self.assertEqual(self.status_of(ad_id), PENDING)
        self.assertEqual([m.chat_id for m in self.bot.sent], [ADMIN_ID])
        self.assertIn(f"№{ad_id}", self.bot.sent[0].text)
        self.assertIsNotNone(self.bot.sent[0].markup)  # кнопки «Одобрить» и «Отклонить»

    def test_auto_approve_publishes_without_notifying(self):
        self.make_client(auto_approve=True)
        response = self.post("/api/listings", json=NEW_AD)
        self.assertEqual(response.json()["status"], ACTIVE)
        self.assertEqual(self.status_of(response.json()["id"]), ACTIVE)
        self.assertEqual(self.bot.sent, [])

    def test_author_comes_from_signature(self):
        ad_id = self.post("/api/listings", user=OTHER, json=NEW_AD).json()["id"]
        ad = asyncio.run(self.db.get_ad(ad_id))
        self.assertEqual((ad["user_id"], ad["author_username"]), (OTHER, "user0002"))

    def test_fields_set_only_by_server_are_forbidden(self):
        for extra in ({"status": "active"}, {"user_id": 5}, {"id": 1}, {"phone": "+375291234567"}):
            with self.subTest(extra=extra):
                response = self.post("/api/listings", json={**NEW_AD, **extra})
                self.assertEqual(response.status_code, 422)
        self.assertEqual(asyncio.run(self.db.stats())["ads"][PENDING], 0)

    def test_same_rules_as_in_bot_with_readable_message(self):
        cases = {
            "title": ("ab", "Название"),
            "description": ("коротко", "Описание"),
            "price": ("   ", "Цена"),
            "location": ("М" * 61, "Район или город"),
            "category": ("nope", "категории"),
        }
        for field, (value, expected) in cases.items():
            with self.subTest(field=field):
                response = self.post("/api/listings", json={**NEW_AD, field: value})
                self.assertEqual(response.status_code, 422)
                self.assertIn(expected, response.json()["detail"])
                self.assertNotIn(
                    value.strip() or "~", response.json()["detail"].replace(expected, "")
                )

    def test_description_is_limited_to_300_characters(self):
        ok = self.post("/api/listings", json={**NEW_AD, "description": "о" * 300})
        too_long = self.post("/api/listings", json={**NEW_AD, "description": "о" * 301})
        self.assertEqual((ok.status_code, too_long.status_code), (201, 422))

    def test_missing_and_oversized_fields_are_rejected(self):
        self.assertEqual(self.post("/api/listings", json={"title": "Сайты"}).status_code, 422)
        huge = self.post("/api/listings", json={**NEW_AD, "title": "а" * 100_000})
        self.assertEqual(huge.status_code, 422)

    def test_limit_of_active_listings(self):
        for _ in range(MAX_LIVE_ADS):
            self.assertEqual(self.post("/api/listings", json=NEW_AD).status_code, 201)
        response = self.post("/api/listings", json=NEW_AD)
        self.assertEqual(response.status_code, 409)
        self.assertIn(str(MAX_LIVE_ADS), response.json()["detail"])
        self.assertEqual(self.post("/api/listings", user=OTHER, json=NEW_AD).status_code, 201)


class RightsTests(ApiTestCase):
    def test_foreign_listing_cannot_be_hidden_shown_or_deleted(self):
        ad_id = self.add_ad(owner=AUTHOR)
        attempts = [
            self.post(f"/api/my/listings/{ad_id}/hide", user=OTHER),
            self.post(f"/api/my/listings/{ad_id}/show", user=OTHER),
            self.delete(f"/api/my/listings/{ad_id}", user=OTHER),
        ]
        self.assertEqual([r.status_code for r in attempts], [404, 404, 404])
        self.assertEqual(self.status_of(ad_id), ACTIVE)

    def test_owner_hides_shows_and_deletes(self):
        ad_id = self.add_ad()
        hidden = self.post(f"/api/my/listings/{ad_id}/hide")
        self.assertEqual((hidden.status_code, hidden.json()["status"]), (200, HIDDEN))
        self.assertEqual(self.get(f"/api/listings/{ad_id}").status_code, 404)
        shown = self.post(f"/api/my/listings/{ad_id}/show")
        self.assertEqual(shown.json()["status"], ACTIVE)
        self.assertEqual(self.delete(f"/api/my/listings/{ad_id}").status_code, 204)
        self.assertIsNone(self.status_of(ad_id))
        self.assertEqual(self.delete(f"/api/my/listings/{ad_id}").status_code, 404)

    def test_showing_cannot_publish_pending_or_rejected_listing(self):
        pending = self.add_ad(status=PENDING)
        rejected = self.add_ad(status="rejected")
        for ad_id, expected in ((pending, PENDING), (rejected, "rejected")):
            self.post(f"/api/my/listings/{ad_id}/show")
            self.post(f"/api/my/listings/{ad_id}/hide")
            self.assertEqual(self.status_of(ad_id), expected)

    def test_showing_respects_limit(self):
        first = self.add_ad()
        self.post(f"/api/my/listings/{first}/hide")
        for _ in range(MAX_LIVE_ADS):
            self.add_ad()
        response = self.post(f"/api/my/listings/{first}/show")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.status_of(first), HIDDEN)

    def test_my_listings_shows_only_own_with_status(self):
        mine = self.add_ad(owner=AUTHOR, status=PENDING)
        self.add_ad(owner=OTHER)
        items = self.get("/api/my/listings").json()
        self.assertEqual([(i["id"], i["status"]) for i in items], [(mine, PENDING)])


class ReportTests(ApiTestCase):
    def test_report_goes_to_admins_once_per_person(self):
        ad_id = self.add_ad()
        first = self.post(f"/api/listings/{ad_id}/report", user=OTHER)
        second = self.post(f"/api/listings/{ad_id}/report", user=OTHER)
        self.assertEqual((first.status_code, second.status_code), (204, 409))
        self.assertEqual([m.chat_id for m in self.bot.sent], [ADMIN_ID])
        self.assertIn(f"/delete {ad_id}", self.bot.sent[0].text)
        self.assertEqual(self.post(f"/api/listings/{ad_id}/report", user=3).status_code, 204)

    def test_cannot_report_unpublished_or_unknown_listing(self):
        pending = self.add_ad(status=PENDING)
        for ad_id in (pending, 999):
            self.assertEqual(self.post(f"/api/listings/{ad_id}/report").status_code, 404)
        self.assertEqual(self.bot.sent, [])


class LimitsAndHeadersTests(ApiTestCase):
    def test_rate_limit_per_person(self):
        self.make_client(rate_limit=2)
        codes = [self.get("/api/listings").status_code for _ in range(3)]
        self.assertEqual(codes, [200, 200, 429])
        self.assertEqual(self.get("/api/listings", user=OTHER).status_code, 200)

    def test_security_headers_on_page_and_no_cache_on_api(self):
        page = self.client.get("/")
        self.assertEqual(page.status_code, 200)
        self.assertIn("frame-ancestors", page.headers["content-security-policy"])
        self.assertEqual(page.headers["x-content-type-options"], "nosniff")
        api = self.client.get("/api/categories")
        self.assertEqual(api.headers["cache-control"], "no-store")

    def test_error_responses_do_not_echo_user_text(self):
        secret = "СЕКРЕТНЫЙ-ТЕКСТ"
        response = self.post("/api/listings", json={**NEW_AD, "title": secret, "price": ""})
        self.assertEqual(response.status_code, 422)
        self.assertNotIn(secret, response.text)


if __name__ == "__main__":
    unittest.main()
