from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from app.display_items import DisplayItemStore, DisplayItemValidationError


class DisplayItemStoreTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.store = DisplayItemStore(Path(self.temporary.name) / "content.db")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_multiple_items_crud_and_ordering(self) -> None:
        bean = self.store.create(
            {
                "name": "九月豆单",
                "content_type": "bean",
                "title": "Ethiopia\nGuji",
                "priority": 2,
                "display_seconds": 12,
            }
        )
        event = self.store.create(
            {
                "name": "周末唱片分享",
                "content_type": "event",
                "title": "LISTENING SESSION",
                "priority": 8,
            }
        )
        self.assertEqual([item["id"] for item in self.store.list()], [event["id"], bean["id"]])

        updated = self.store.update(bean["id"], {"callout": "Available on filter"})
        self.assertIsNotNone(updated)
        self.assertEqual(updated["callout"], "Available on filter")
        self.assertTrue(self.store.delete(event["id"]))
        self.assertEqual([item["id"] for item in self.store.list()], [bean["id"]])

    def test_eligible_items_use_enabled_and_date_range(self) -> None:
        active = self.store.create(
            {
                "name": "当前内容",
                "title": "CURRENT",
                "active_from": "2026-09-01",
                "active_until": "2026-09-30",
            }
        )
        self.store.create(
            {
                "name": "未来内容",
                "title": "FUTURE",
                "active_from": "2026-10-01",
            }
        )
        self.store.create({"name": "停用内容", "title": "OFF", "enabled": False})
        self.assertEqual(
            [item["id"] for item in self.store.list_eligible(date(2026, 9, 3))],
            [active["id"]],
        )

    def test_validation_rejects_invalid_ranges_and_duration(self) -> None:
        with self.assertRaises(DisplayItemValidationError):
            self.store.create(
                {
                    "name": "错误日期",
                    "title": "INVALID",
                    "active_from": "2026-10-02",
                    "active_until": "2026-10-01",
                }
            )
        with self.assertRaises(DisplayItemValidationError):
            self.store.create({"name": "错误时长", "title": "INVALID", "display_seconds": 2})

    def test_image_item_can_omit_text_title(self) -> None:
        item = self.store.create(
            {
                "name": "活动图片",
                "content_type": "event",
                "image_url": "/media/weekend-event.png",
            }
        )
        self.assertEqual(item["title"], "")
        self.assertEqual(item["image_url"], "/media/weekend-event.png")
        with self.assertRaises(DisplayItemValidationError):
            self.store.create(
                {
                    "name": "错误图片地址",
                    "image_url": "file:///Users/example/event.png",
                }
            )

    def test_legacy_promotion_migrates_only_once(self) -> None:
        legacy = {
            "kind": "bean",
            "eyebrow": "NEW BEAN",
            "title": "Ethiopia\nGuji",
            "details": "JASMINE",
            "callout": "Available on filter",
            "footer": "ASK THE BARISTA",
        }
        migrated = self.store.migrate_legacy_promotion(legacy)
        self.assertIsNotNone(migrated)
        self.assertEqual(len(self.store.list()), 1)
        self.assertTrue(self.store.delete(migrated["id"]))
        self.assertIsNone(self.store.migrate_legacy_promotion(legacy))
        self.assertEqual(self.store.list(), [])


if __name__ == "__main__":
    unittest.main()
