"""Тесты проверки initData, лимита запросов и доступа."""

import hashlib
import hmac
import json
import unittest
from urllib.parse import urlencode

from webapp.auth import (
    CLOCK_SKEW_SECONDS,
    MAX_AUTH_AGE_SECONDS,
    MAX_INIT_DATA_LENGTH,
    AuthError,
    RateLimiter,
    is_member,
    validate_init_data,
)

BOT_TOKEN = "123456:TEST-TOKEN-NOT-REAL"
NOW = 1_800_000_000
USER = {"id": 777, "first_name": "Анна", "username": "anna"}


def sign(fields: dict[str, str], token: str = BOT_TOKEN) -> str:
    """Собирает initData так же, как это делает Telegram (отдельная копия алгоритма для теста)."""
    check_string = "\n".join(f"{key}={fields[key]}" for key in sorted(fields))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    signature = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()
    return urlencode({**fields, "hash": signature})


def make_init_data(user=USER, auth_date=NOW, token=BOT_TOKEN, **extra) -> str:
    fields = {"auth_date": str(auth_date), "query_id": "AAH", **extra}
    if user is not None:
        fields["user"] = user if isinstance(user, str) else json.dumps(user, ensure_ascii=False)
    return sign(fields, token)


def check(init_data: str, now: float = NOW):
    return validate_init_data(init_data, BOT_TOKEN, now=now)


class ValidInitDataTests(unittest.TestCase):
    def test_valid_data_returns_user(self):
        user = check(make_init_data())
        self.assertEqual((user.id, user.first_name, user.username), (777, "Анна", "anna"))

    def test_user_without_username(self):
        user = check(make_init_data(user={"id": 5, "first_name": "Иван"}))
        self.assertIsNone(user.username)

    def test_data_just_inside_lifetime_is_accepted(self):
        check(make_init_data(auth_date=NOW - MAX_AUTH_AGE_SECONDS + 1))

    def test_small_clock_skew_is_accepted(self):
        check(make_init_data(auth_date=NOW + CLOCK_SKEW_SECONDS))

    def test_server_clock_few_minutes_behind_is_accepted(self):
        check(make_init_data(auth_date=NOW + 4 * 60))


class ForgeryTests(unittest.TestCase):
    def test_signed_with_another_token_is_rejected(self):
        with self.assertRaises(AuthError):
            check(make_init_data(token="999:OTHER-TOKEN"))

    def test_swapping_user_after_signing_is_rejected(self):
        # Злоумышленник берёт свою верную строку и подставляет чужой номер, подпись остаётся
        genuine = make_init_data()
        forged = genuine.replace("777", "888")
        self.assertNotEqual(genuine, forged)
        with self.assertRaises(AuthError):
            check(forged)

    def test_foreign_user_with_own_valid_signature_gets_own_id_only(self):
        # Чужая подлинная строка даёт чужой номер, но не позволяет выдать себя за другого
        other = check(make_init_data(user={"id": 888, "first_name": "Пётр"}))
        self.assertEqual(other.id, 888)
        self.assertNotEqual(other.id, check(make_init_data()).id)

    def test_adding_a_field_after_signing_is_rejected(self):
        with self.assertRaises(AuthError):
            check(make_init_data() + "&start_param=admin")

    def test_missing_or_broken_hash_is_rejected(self):
        genuine = make_init_data()
        without_hash = "&".join(p for p in genuine.split("&") if not p.startswith("hash="))
        non_ascii_hash = without_hash + "&hash=%D0%B0%D0%B1%D0%B2"
        for data in (
            without_hash,
            non_ascii_hash,
            without_hash + "&hash=",
            without_hash + "&hash=0",
        ):
            with self.subTest(data=data[-20:]), self.assertRaises(AuthError):
                check(data)

    def test_empty_and_oversized_data_is_rejected(self):
        for data in ("", "a" * (MAX_INIT_DATA_LENGTH + 1)):
            with self.subTest(length=len(data)), self.assertRaises(AuthError):
                check(data)


class FreshnessTests(unittest.TestCase):
    def test_expired_data_is_rejected(self):
        with self.assertRaises(AuthError):
            check(make_init_data(auth_date=NOW - MAX_AUTH_AGE_SECONDS - 1))

    def test_data_from_the_future_is_rejected(self):
        with self.assertRaises(AuthError):
            check(make_init_data(auth_date=NOW + CLOCK_SKEW_SECONDS + 1))

    def test_missing_or_broken_date_is_rejected(self):
        no_date = sign({"user": json.dumps(USER)})
        bad_date = sign({"user": json.dumps(USER), "auth_date": "вчера"})
        for data in (no_date, bad_date):
            with self.assertRaises(AuthError):
                check(data)


class UserFieldTests(unittest.TestCase):
    def test_broken_user_field_is_rejected(self):
        cases = {
            "нет user": None,
            "не JSON": "{oops",
            "список": "[1, 2]",
            "число": "5",
            "нет id": json.dumps({"first_name": "Анна"}),
            "id строкой": json.dumps({"id": "777"}),
            "id логический": json.dumps({"id": True}),
            "id ноль": json.dumps({"id": 0}),
            "id отрицательный": json.dumps({"id": -5}),
        }
        for name, user in cases.items():
            with self.subTest(case=name), self.assertRaises(AuthError):
                check(make_init_data(user=user))


class RateLimiterTests(unittest.TestCase):
    def setUp(self):
        self.now = 1000.0
        self.limiter = RateLimiter(limit=3, window=60, clock=lambda: self.now)

    def test_blocks_after_limit(self):
        self.assertEqual([self.limiter.allow(1) for _ in range(4)], [True, True, True, False])

    def test_window_slides(self):
        for _ in range(3):
            self.limiter.allow(1)
        self.now += 59
        self.assertFalse(self.limiter.allow(1))
        self.now += 1
        self.assertTrue(self.limiter.allow(1))

    def test_users_are_counted_separately(self):
        for _ in range(3):
            self.limiter.allow(1)
        self.assertFalse(self.limiter.allow(1))
        self.assertTrue(self.limiter.allow(2))

    def test_blocked_requests_do_not_extend_the_block(self):
        for _ in range(3):
            self.limiter.allow(1)
        for _ in range(10):
            self.limiter.allow(1)  # отклонённые попытки не считаются
        self.now += 60
        self.assertTrue(self.limiter.allow(1))

    def test_default_limit_is_thirty_per_minute(self):
        limiter = RateLimiter(clock=lambda: 0.0)
        results = [limiter.allow(1) for _ in range(31)]
        self.assertEqual((results.count(True), results[-1]), (30, False))


class MembershipTests(unittest.IsolatedAsyncioTestCase):
    async def test_everyone_is_a_member_for_now(self):
        self.assertTrue(await is_member(777))


if __name__ == "__main__":
    unittest.main()
