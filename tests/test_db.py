"""Тесты базы данных: создание, одобрение, лимит, страницы, удаление, жалобы."""

import tempfile
import unittest
from pathlib import Path

from bot.config import MAX_LIVE_ADS, PAGE_SIZE
from bot.db import ACTIVE, HIDDEN, PENDING, REJECTED, Database, LimitReached, page_count

AD_FIELDS = {
    "category": "it",
    "title": "Сайты",
    "description": "Делаю сайты под ключ",
    "price": "от 300 BYN",
    "location": "Минск",
}


class DatabaseTestCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self._folder = tempfile.TemporaryDirectory()
        self.addCleanup(self._folder.cleanup)
        # Вложенная папка проверяет, что база сама создаёт недостающие папки
        self.db = Database(Path(self._folder.name) / "nested" / "test.db")
        await self.db.init()
        await self.add_user(1)

    async def add_user(self, user_id: int) -> None:
        await self.db.save_user(user_id, f"user{user_id}", f"Имя{user_id}")

    async def add_ad(self, user_id: int = 1, auto_approve: bool = False, **changes) -> int:
        return await self.db.create_ad(user_id, {**AD_FIELDS, **changes}, auto_approve)

    async def add_many_active(self, count: int) -> None:
        """Создаёт count опубликованных объявлений, раздавая их разным авторам из-за лимита."""
        for number in range(count):
            user_id = 100 + number // MAX_LIVE_ADS
            await self.add_user(user_id)
            await self.add_ad(user_id, auto_approve=True, title=f"Объявление {number}")


class CreateAndApproveTests(DatabaseTestCase):
    async def test_new_ad_waits_for_review(self):
        ad_id = await self.add_ad()
        ad = await self.db.get_ad(ad_id)
        self.assertEqual(ad["status"], PENDING)
        self.assertEqual(ad["author_name"], "Имя1")
        self.assertIsNone(ad["phone"])

    async def test_auto_approve_publishes_at_once(self):
        ad_id = await self.add_ad(auto_approve=True)
        self.assertEqual((await self.db.get_ad(ad_id))["status"], ACTIVE)

    async def test_pending_ad_is_not_in_catalog_until_approved(self):
        ad_id = await self.add_ad()
        self.assertEqual((await self.db.list_by_category("it"))[1], 0)
        self.assertEqual([ad["id"] for ad in await self.db.list_pending()], [ad_id])

        self.assertTrue(await self.db.set_status(ad_id, ACTIVE))
        ads, total = await self.db.list_by_category("it")
        self.assertEqual((total, [ad["id"] for ad in ads]), (1, [ad_id]))
        self.assertEqual(await self.db.list_pending(), [])

    async def test_rejected_ad_is_not_in_catalog(self):
        ad_id = await self.add_ad()
        await self.db.set_status(ad_id, REJECTED)
        self.assertEqual((await self.db.list_by_category("it"))[1], 0)

    async def test_unknown_ad_status_change_returns_false(self):
        self.assertFalse(await self.db.set_status(999, ACTIVE))

    async def test_owner_cannot_change_foreign_ad(self):
        await self.add_user(2)
        ad_id = await self.add_ad(auto_approve=True)
        self.assertFalse(await self.db.set_status(ad_id, HIDDEN, owner_id=2))
        self.assertTrue(await self.db.set_status(ad_id, HIDDEN, owner_id=1))

    async def test_phone_is_saved(self):
        ad_id = await self.add_ad(phone="+375 29 123-45-67")
        self.assertEqual((await self.db.get_ad(ad_id))["phone"], "+375 29 123-45-67")


class LimitTests(DatabaseTestCase):
    async def fill_limit(self) -> list[int]:
        return [await self.add_ad() for _ in range(MAX_LIVE_ADS)]

    async def test_limit_blocks_extra_ad(self):
        await self.fill_limit()
        with self.assertRaises(LimitReached):
            await self.add_ad()
        self.assertEqual(await self.db.count_live_ads(1), MAX_LIVE_ADS)

    async def test_limit_is_per_user(self):
        await self.fill_limit()
        await self.add_user(2)
        await self.add_ad(user_id=2)

    async def test_hidden_ad_frees_a_slot(self):
        ids = await self.fill_limit()
        await self.db.set_status(ids[0], HIDDEN)
        await self.add_ad()

    async def test_showing_hidden_ad_respects_limit(self):
        ids = await self.fill_limit()
        await self.db.set_status(ids[0], HIDDEN)
        await self.add_ad()
        with self.assertRaises(LimitReached):
            await self.db.set_status(ids[0], ACTIVE)

    async def test_approving_pending_ad_does_not_hit_limit(self):
        ids = await self.fill_limit()
        self.assertTrue(await self.db.set_status(ids[0], ACTIVE))

    async def test_rejected_ad_frees_a_slot(self):
        ids = await self.fill_limit()
        await self.db.set_status(ids[0], REJECTED)
        await self.add_ad()


class PaginationTests(DatabaseTestCase):
    def test_page_count(self):
        self.assertEqual(page_count(0), 1)
        self.assertEqual(page_count(1), 1)
        self.assertEqual(page_count(PAGE_SIZE), 1)
        self.assertEqual(page_count(PAGE_SIZE + 1), 2)

    async def test_pages_split_ads_without_overlap(self):
        total_ads = PAGE_SIZE * 2 + 3
        await self.add_many_active(total_ads)

        first, total = await self.db.list_by_category("it", 0)
        second, _ = await self.db.list_by_category("it", 1)
        third, _ = await self.db.list_by_category("it", 2)
        beyond, _ = await self.db.list_by_category("it", 3)

        self.assertEqual(total, total_ads)
        self.assertEqual(
            [len(first), len(second), len(third), len(beyond)], [PAGE_SIZE, PAGE_SIZE, 3, 0]
        )
        ids = [ad["id"] for ad in first + second + third]
        self.assertEqual(len(set(ids)), total_ads)
        self.assertEqual(ids, sorted(ids, reverse=True))  # новые объявления первыми

    async def test_other_category_is_not_mixed_in(self):
        await self.add_ad(auto_approve=True, category="beauty")
        self.assertEqual((await self.db.list_by_category("it"))[1], 0)
        self.assertEqual((await self.db.list_by_category("beauty"))[1], 1)


class SearchTests(DatabaseTestCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        await self.add_ad(auto_approve=True, title="Ремонт ноутбуков", description="Быстро")
        await self.add_user(2)
        await self.add_ad(
            2,
            auto_approve=True,
            category="beauty",
            title="Маникюр",
            description="Недорого, РЕМОНТ ногтей",
        )
        await self.add_user(3)
        await self.add_ad(3, title="Ремонт скрытый", description="На проверке")  # не опубликовано

    async def titles(self, **kwargs) -> list[str]:
        ads, _ = await self.db.search(**kwargs)
        return sorted(ad["title"] for ad in ads)

    async def test_without_filters_lists_all_published_categories(self):
        self.assertEqual(await self.titles(), ["Маникюр", "Ремонт ноутбуков"])

    async def test_query_ignores_case_for_cyrillic(self):
        for query in ("ремонт", "РЕМОНТ", "РеМоНт"):
            with self.subTest(query=query):
                self.assertEqual(await self.titles(query=query), ["Маникюр", "Ремонт ноутбуков"])

    async def test_query_searches_title_and_description(self):
        self.assertEqual(await self.titles(query="недорого"), ["Маникюр"])
        self.assertEqual(await self.titles(query="ноутбук"), ["Ремонт ноутбуков"])

    async def test_query_and_category_are_combined(self):
        self.assertEqual(await self.titles(category="it", query="ремонт"), ["Ремонт ноутбуков"])
        self.assertEqual(await self.titles(category="beauty", query="ноутбук"), [])

    async def test_pending_ads_are_never_found(self):
        self.assertEqual(await self.titles(query="скрытый"), [])

    async def test_special_characters_are_searched_as_plain_text(self):
        for query in ("%", "_", "'; DROP TABLE ads; --"):
            with self.subTest(query=query):
                self.assertEqual(await self.titles(query=query), [])
        self.assertEqual((await self.db.stats())["ads"][ACTIVE], 2)

    async def test_total_counts_all_matches_not_just_page(self):
        await self.add_many_active(PAGE_SIZE + 2)
        ads, total = await self.db.search(query="Объявление", page=0)
        self.assertEqual((len(ads), total), (PAGE_SIZE, PAGE_SIZE + 2))
        rest, _ = await self.db.search(query="Объявление", page=1)
        self.assertEqual(len(rest), 2)


class SetHiddenTests(DatabaseTestCase):
    async def status(self, ad_id: int) -> str:
        return (await self.db.get_ad(ad_id))["status"]

    async def test_owner_hides_and_shows_own_ad(self):
        ad_id = await self.add_ad(auto_approve=True)
        self.assertEqual((await self.db.set_hidden(ad_id, 1, hidden=True))["status"], HIDDEN)
        self.assertEqual((await self.db.set_hidden(ad_id, 1, hidden=False))["status"], ACTIVE)

    async def test_foreign_or_missing_ad_returns_none_and_changes_nothing(self):
        await self.add_user(2)
        ad_id = await self.add_ad(auto_approve=True)
        self.assertIsNone(await self.db.set_hidden(ad_id, 2, hidden=True))
        self.assertIsNone(await self.db.set_hidden(999, 1, hidden=True))
        self.assertEqual(await self.status(ad_id), ACTIVE)

    async def test_pending_and_rejected_ads_cannot_be_published_by_showing(self):
        pending = await self.add_ad()
        rejected = await self.add_ad()
        await self.db.set_status(rejected, REJECTED)
        for ad_id, expected in ((pending, PENDING), (rejected, REJECTED)):
            with self.subTest(ad=ad_id):
                await self.db.set_hidden(ad_id, 1, hidden=False)
                await self.db.set_hidden(ad_id, 1, hidden=True)
                self.assertEqual(await self.status(ad_id), expected)

    async def test_showing_respects_limit(self):
        ids = [await self.add_ad(auto_approve=True) for _ in range(MAX_LIVE_ADS)]
        await self.db.set_hidden(ids[0], 1, hidden=True)
        await self.add_ad()
        with self.assertRaises(LimitReached):
            await self.db.set_hidden(ids[0], 1, hidden=False)
        self.assertEqual(await self.status(ids[0]), HIDDEN)


class DeleteTests(DatabaseTestCase):
    async def test_admin_deletes_any_ad(self):
        ad_id = await self.add_ad()
        self.assertTrue(await self.db.delete_ad(ad_id))
        self.assertIsNone(await self.db.get_ad(ad_id))

    async def test_owner_deletes_only_own_ad(self):
        await self.add_user(2)
        ad_id = await self.add_ad()
        self.assertFalse(await self.db.delete_ad(ad_id, owner_id=2))
        self.assertIsNotNone(await self.db.get_ad(ad_id))
        self.assertTrue(await self.db.delete_ad(ad_id, owner_id=1))

    async def test_deleting_missing_ad_returns_false(self):
        self.assertFalse(await self.db.delete_ad(999))

    async def test_deleting_frees_a_slot(self):
        ids = [await self.add_ad() for _ in range(MAX_LIVE_ADS)]
        await self.db.delete_ad(ids[0])
        await self.add_ad()


class UserListAndStatsTests(DatabaseTestCase):
    async def test_user_sees_only_own_ads_newest_first(self):
        await self.add_user(2)
        first = await self.add_ad()
        await self.add_ad(user_id=2)
        second = await self.add_ad()
        own = await self.db.list_by_user(1)
        self.assertEqual([ad["id"] for ad in own], [second, first])

    async def test_stats_count_users_and_statuses(self):
        await self.add_user(2)
        await self.add_ad()
        await self.add_ad(auto_approve=True)
        rejected = await self.add_ad()
        await self.db.set_status(rejected, REJECTED)

        stats = await self.db.stats()
        self.assertEqual(stats["users"], 2)
        self.assertEqual(stats["ads"], {PENDING: 1, ACTIVE: 1, REJECTED: 1, HIDDEN: 0})

    async def test_user_name_is_updated(self):
        await self.db.save_user(1, "new_name", "Новое имя")
        ad = await self.db.get_ad(await self.add_ad())
        self.assertEqual((ad["author_username"], ad["author_name"]), ("new_name", "Новое имя"))


class ReportTests(DatabaseTestCase):
    async def test_second_report_from_same_user_is_ignored(self):
        ad_id = await self.add_ad(auto_approve=True)
        self.assertTrue(await self.db.add_report(5, ad_id))
        self.assertFalse(await self.db.add_report(5, ad_id))

    async def test_other_user_can_report_same_ad(self):
        ad_id = await self.add_ad(auto_approve=True)
        await self.db.add_report(5, ad_id)
        self.assertTrue(await self.db.add_report(6, ad_id))

    async def test_reports_are_removed_with_ad(self):
        ad_id = await self.add_ad(auto_approve=True)
        await self.db.add_report(5, ad_id)
        await self.db.delete_ad(ad_id)
        # Новое объявление может получить тот же номер, и жалобы старого с ним не связаны
        self.assertTrue(await self.db.add_report(5, ad_id))


if __name__ == "__main__":
    unittest.main()
