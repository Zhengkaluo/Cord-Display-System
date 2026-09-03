from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from app.artist_events import ArtistEventStore, artist_name_candidates, normalize_artist_name


class ArtistEventStoreTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.store = ArtistEventStore(Path(self.temporary.name) / "events.db")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_name_normalization_and_collaboration_split(self) -> None:
        self.assertEqual(normalize_artist_name("  CHILDＳ!  "), "childs")
        self.assertEqual(
            artist_name_candidates("Childs feat. Yui / Guest"),
            {"childs feat yui guest", "childs", "yui", "guest"},
        )

    def test_match_uses_aliases_dates_and_priority(self) -> None:
        self.store.create(
            {
                "artist_name": "Childs",
                "aliases": ["孩子乐队"],
                "event_date": "2026-09-20",
                "venue": "A Hall",
                "priority": 0,
            }
        )
        preferred = self.store.create(
            {
                "artist_name": "Childs",
                "event_date": "2026-09-22",
                "venue": "B Hall",
                "priority": 10,
            }
        )
        alias_match = self.store.find_match("Yui & 孩子乐队", date(2026, 9, 3))
        self.assertIsNotNone(alias_match)
        self.assertEqual(alias_match["venue"], "A Hall")
        matched = self.store.find_match("Childs feat. Yui", date(2026, 9, 3))
        self.assertIsNotNone(matched)
        self.assertEqual(matched["id"], preferred["id"])
        self.assertIsNone(self.store.find_match("Childs", date(2026, 9, 23)))

    def test_disabled_event_does_not_match(self) -> None:
        self.store.create(
            {
                "artist_name": "Radiohead",
                "event_date": "2099-01-01",
                "enabled": False,
            }
        )
        self.assertIsNone(self.store.find_match("Radiohead", date(2026, 9, 3)))


if __name__ == "__main__":
    unittest.main()
