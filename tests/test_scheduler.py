from __future__ import annotations

import unittest

from app.state_store import StateStore


def display_item(item_id: int, name: str, title: str) -> dict:
    return {
        "id": item_id,
        "name": name,
        "content_type": "bean",
        "eyebrow": "CORD UPDATE",
        "title": title,
        "details": "DETAILS",
        "callout": "ASK THE BARISTA",
        "footer": "CORD COFFEE",
        "image_url": "",
        "display_seconds": 10,
    }


class AutoInsertSchedulerTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.items = [
            display_item(1, "第一条", "FIRST"),
            display_item(2, "第二条", "SECOND"),
        ]
        self.store = StateStore(display_item_provider=lambda: self.items)
        self.store.update_config(
            {
                "auto_insert_enabled": True,
                "insert_min_interval_minutes": 0,
                "non_music_hourly_max_percent": 10,
            }
        )

    def tearDown(self) -> None:
        self.store.close()

    def _set_track(self, title: str, position: float, duration: float = 100) -> dict:
        return self.store.update_track(
            {
                "title": title,
                "artist": "Artist",
                "album": "Album",
                "source_track_id": title,
                "position": position,
                "duration": duration,
                "playback_status": "playing",
            }
        )

    def test_natural_track_change_starts_insert_then_returns_to_latest_track(self) -> None:
        self._set_track("Track A", 95)
        inserted = self._set_track("Track B", 0)
        self.assertEqual(inserted["display"]["mode"], "promotion")
        self.assertEqual(inserted["display"]["insert_source"], "scheduler")
        self.assertEqual(inserted["display"]["display_item_id"], 1)

        during_insert = self._set_track("Track C", 12)
        self.assertEqual(during_insert["display"]["display_item_id"], 1)
        returned = self.store.finish_scheduled_insert()
        self.assertEqual(returned["track"]["title"], "Track C")
        self.assertEqual(returned["display"]["mode"], "now_playing")
        self.assertIsNone(returned["display"]["insert_source"])

    def test_content_rotates_after_each_eligible_natural_end(self) -> None:
        self._set_track("Track A", 99)
        first = self._set_track("Track B", 0)
        self.assertEqual(first["display"]["display_item_id"], 1)
        self.store.finish_scheduled_insert()

        self._set_track("Track B", 99)
        second = self._set_track("Track C", 0)
        self.assertEqual(second["display"]["display_item_id"], 2)

    def test_pause_and_mid_track_skip_do_not_insert(self) -> None:
        self._set_track("Track A", 30)
        paused = self.store.update_track({"playback_status": "paused"})
        self.assertNotEqual(paused["display"].get("insert_source"), "scheduler")

        self.store.update_track({"playback_status": "playing"})
        skipped = self._set_track("Track B", 0)
        self.assertNotEqual(skipped["display"].get("insert_source"), "scheduler")

    def test_missing_position_can_use_observed_full_duration(self) -> None:
        self.store.update_track(
            {
                "title": "Track A",
                "artist": "Artist",
                "source_track_id": "Track A",
                "position": None,
                "duration": 100,
                "playback_status": "playing",
            }
        )
        self.store._observed_playing_seconds = 99
        inserted = self.store.update_track(
            {
                "title": "Track B",
                "source_track_id": "Track B",
                "position": None,
                "duration": 120,
                "playback_status": "playing",
            }
        )
        self.assertEqual(inserted["display"]["insert_source"], "scheduler")

    def test_disabled_or_zero_budget_prevents_insert(self) -> None:
        self.store.update_config({"auto_insert_enabled": False})
        self._set_track("Track A", 99)
        disabled = self._set_track("Track B", 0)
        self.assertNotEqual(disabled["display"].get("insert_source"), "scheduler")

        self.store.update_config(
            {"auto_insert_enabled": True, "non_music_hourly_max_percent": 0}
        )
        self._set_track("Track B", 99)
        no_budget = self._set_track("Track C", 0)
        self.assertNotEqual(no_budget["display"].get("insert_source"), "scheduler")

    def test_minimum_interval_blocks_the_next_track_end(self) -> None:
        self.store.update_config({"insert_min_interval_minutes": 20})
        self._set_track("Track A", 99)
        first = self._set_track("Track B", 0)
        self.assertEqual(first["display"]["insert_source"], "scheduler")
        self.store.finish_scheduled_insert()

        self._set_track("Track B", 99)
        blocked = self._set_track("Track C", 0)
        self.assertNotEqual(blocked["display"].get("insert_source"), "scheduler")

    def test_hourly_budget_blocks_an_insert_that_would_exceed_the_cap(self) -> None:
        self.store.update_config({"non_music_hourly_max_percent": 0.5})
        self._set_track("Track A", 99)
        first = self._set_track("Track B", 0)
        self.assertEqual(first["display"]["insert_source"], "scheduler")
        self.store.finish_scheduled_insert()

        self._set_track("Track B", 99)
        blocked = self._set_track("Track C", 0)
        self.assertNotEqual(blocked["display"].get("insert_source"), "scheduler")


if __name__ == "__main__":
    unittest.main()
