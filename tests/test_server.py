from __future__ import annotations

import json
import tempfile
import threading
import unittest
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from app.server import create_server


class ServerTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.media_temp = tempfile.TemporaryDirectory()
        cls.config_path = Path(cls.media_temp.name) / "runtime-config.json"
        cls.database_path = Path(cls.media_temp.name) / "events.db"
        cls.server = create_server(
            "127.0.0.1",
            0,
            media_root=Path(cls.media_temp.name),
            config_path=cls.config_path,
            database_path=cls.database_path,
        )
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)
        cls.media_temp.cleanup()

    def get_json(self, path: str) -> dict:
        with urlopen(f"{self.base_url}{path}", timeout=2) as response:
            self.assertEqual(response.headers.get_content_type(), "application/json")
            return json.loads(response.read().decode("utf-8"))

    def post_json(self, path: str, payload: dict) -> dict:
        request = Request(
            f"{self.base_url}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=2) as response:
            return json.loads(response.read().decode("utf-8"))

    def put_media(self, filename: str, content_type: str, data: bytes) -> dict:
        request = Request(
            f"{self.base_url}/api/media",
            data=data,
            headers={
                "Content-Type": content_type,
                "X-Filename": filename,
            },
            method="PUT",
        )
        with urlopen(request, timeout=2) as response:
            self.assertEqual(response.status, 201)
            return json.loads(response.read().decode("utf-8"))

    def request_json(self, path: str, method: str, payload: dict | None = None) -> dict:
        request = Request(
            f"{self.base_url}{path}",
            data=None if payload is None else json.dumps(payload).encode("utf-8"),
            headers={} if payload is None else {"Content-Type": "application/json"},
            method=method,
        )
        with urlopen(request, timeout=2) as response:
            return json.loads(response.read().decode("utf-8"))

    def test_health(self) -> None:
        health = self.get_json("/health")
        self.assertTrue(health["ok"])
        self.assertEqual(health["schema_version"], "1.0")

    def test_state_contract(self) -> None:
        state = self.get_json("/api/state")
        self.assertEqual(set(state), {"schema_version", "revision", "updated_at", "track", "display", "content", "config", "system"})
        self.assertIn("position", state["track"])
        self.assertIn("duration", state["track"])
        self.assertIn("source_track_id", state["track"])
        self.assertIn("position_accuracy", state["track"])
        self.assertIn("platform", state["system"])
        self.assertIn("message", state["system"])
        self.assertIn("artist_notice", state["content"])
        self.assertIn("promotion", state["content"])
        self.assertIn("auto_insert_enabled", state["config"])
        self.assertIn("insert_min_interval_minutes", state["config"])

    def test_track_update_changes_revision(self) -> None:
        before = self.get_json("/api/state")
        after = self.post_json(
            "/api/mock/track",
            {"title": "Test Track", "artist": "CORD", "position": 12, "duration": 120},
        )
        self.assertGreater(after["revision"], before["revision"])
        self.assertEqual(after["track"]["title"], "Test Track")
        self.assertEqual(after["track"]["position"], 12.0)

    def test_invalid_track_update_is_rejected(self) -> None:
        request = Request(
            f"{self.base_url}/api/mock/track",
            data=json.dumps({"duration": -1}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with self.assertRaises(HTTPError) as raised:
            urlopen(request, timeout=2)
        self.assertEqual(raised.exception.code, 422)

    def test_source_mode_validation(self) -> None:
        state = self.post_json("/api/config", {"source_mode": "auto"})
        self.assertEqual(state["config"]["source_mode"], "auto")

    def test_visual_mode_configuration(self) -> None:
        state = self.post_json(
            "/api/config",
            {"visual_mode": "image", "visual_url": "/media/ambient.png"},
        )
        self.assertEqual(state["config"]["visual_mode"], "image")
        self.assertEqual(state["config"]["visual_url"], "/media/ambient.png")
        persisted = json.loads(self.config_path.read_text(encoding="utf-8"))
        self.assertEqual(persisted["config"]["visual_mode"], "image")
        self.assertEqual(persisted["config"]["visual_url"], "/media/ambient.png")

    def test_display_scene_preview(self) -> None:
        for mode in ("now_playing", "artist_notice", "promotion"):
            state = self.post_json("/api/display", {"mode": mode})
            self.assertEqual(state["display"]["mode"], mode)

    def test_artist_event_crud_and_automatic_match(self) -> None:
        event = self.request_json(
            "/api/artist-events",
            "POST",
            {
                "artist_name": "Childs",
                "aliases": ["孩子乐队"],
                "event_date": "2099-09-12",
                "time_label": "20:00",
                "venue": "HOU LIVE",
                "city": "SHENZHEN",
                "priority": 5,
                "enabled": True,
            },
        )
        self.assertEqual(event["date_label"], "SEP 12")
        listing = self.get_json("/api/artist-events")
        self.assertTrue(any(item["id"] == event["id"] for item in listing["items"]))

        self.post_json("/api/display", {"control_mode": "auto"})
        matched = self.post_json(
            "/api/mock/track",
            {"title": "Intro", "artist": "Yui feat. 孩子乐队", "playback_status": "playing"},
        )
        self.assertEqual(matched["display"]["mode"], "artist_notice")
        self.assertEqual(matched["display"]["artist_event_id"], event["id"])
        self.assertEqual(matched["content"]["artist_notice"]["venue"], "HOU LIVE")

        updated = self.request_json(
            f"/api/artist-events/{event['id']}",
            "PUT",
            {"venue": "NUBOND LIVEHOUSE"},
        )
        self.assertEqual(updated["venue"], "NUBOND LIVEHOUSE")
        current = self.get_json("/api/state")
        self.assertEqual(current["content"]["artist_notice"]["venue"], "NUBOND LIVEHOUSE")

        self.request_json(f"/api/artist-events/{event['id']}", "DELETE")
        current = self.get_json("/api/state")
        self.assertEqual(current["display"]["mode"], "now_playing")

    def test_display_item_crud_multiple_records_and_preview(self) -> None:
        bean = self.request_json(
            "/api/display-items",
            "POST",
            {
                "name": "九月豆单",
                "content_type": "bean",
                "eyebrow": "NEW BEAN · CURRENT ROTATION",
                "title": "Ethiopia\nGuji",
                "details": "JASMINE · BERGAMOT",
                "display_seconds": 12,
                "priority": 3,
            },
        )
        event = self.request_json(
            "/api/display-items",
            "POST",
            {
                "name": "周末唱片分享",
                "content_type": "event",
                "eyebrow": "AT CORD THIS WEEKEND",
                "title": "LISTENING SESSION",
                "details": "SAT · 15:00",
                "display_seconds": 8,
                "priority": 7,
            },
        )
        image = self.request_json(
            "/api/display-items",
            "POST",
            {
                "name": "活动图片",
                "content_type": "event",
                "image_url": "/media/weekend-event.png",
                "display_seconds": 10,
            },
        )
        listing = self.get_json("/api/display-items")
        listed_ids = {item["id"] for item in listing["items"]}
        self.assertTrue({bean["id"], event["id"], image["id"]}.issubset(listed_ids))

        preview = self.post_json(f"/api/display-items/{event['id']}/preview", {})
        self.assertEqual(preview["display"]["mode"], "promotion")
        self.assertEqual(preview["display"]["control_mode"], "manual")
        self.assertEqual(preview["display"]["display_item_id"], event["id"])
        self.assertEqual(preview["content"]["promotion"]["kind"], "event")
        self.assertEqual(preview["content"]["promotion"]["title"], "LISTENING SESSION")

        image_preview = self.post_json(f"/api/display-items/{image['id']}/preview", {})
        self.assertEqual(
            image_preview["content"]["promotion"]["image_url"],
            "/media/weekend-event.png",
        )
        self.assertEqual(image_preview["content"]["promotion"]["title"], "")

        updated = self.request_json(
            f"/api/display-items/{bean['id']}",
            "PUT",
            {"enabled": False, "display_seconds": 15},
        )
        self.assertFalse(updated["enabled"])
        self.assertEqual(updated["display_seconds"], 15)

        self.request_json(f"/api/display-items/{bean['id']}", "DELETE")
        self.request_json(f"/api/display-items/{event['id']}", "DELETE")
        self.request_json(f"/api/display-items/{image['id']}", "DELETE")

    def test_invalid_display_scene_is_rejected(self) -> None:
        request = Request(
            f"{self.base_url}/api/display",
            data=json.dumps({"mode": "unknown"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with self.assertRaises(HTTPError) as raised:
            urlopen(request, timeout=2)
        self.assertEqual(raised.exception.code, 422)

    def test_scene_content_update_is_persisted(self) -> None:
        state = self.post_json(
            "/api/content/artist_notice",
            {"date_label": "OCT 03", "venue": "NUBOND LIVEHOUSE"},
        )
        self.assertEqual(state["content"]["artist_notice"]["date_label"], "OCT 03")
        self.assertEqual(state["content"]["artist_notice"]["venue"], "NUBOND LIVEHOUSE")
        persisted = json.loads(self.config_path.read_text(encoding="utf-8"))
        self.assertEqual(persisted["content"]["artist_notice"]["date_label"], "OCT 03")

    def test_media_upload_and_range_response(self) -> None:
        payload = b"0123456789"
        uploaded = self.put_media("ambient.mp4", "video/mp4", payload)
        self.assertEqual(uploaded["media_type"], "video")
        self.assertEqual(uploaded["url"], "/media/ambient.mp4")

        request = Request(
            f"{self.base_url}{uploaded['url']}",
            headers={"Range": "bytes=2-5"},
        )
        with urlopen(request, timeout=2) as response:
            self.assertEqual(response.status, 206)
            self.assertEqual(response.headers["Content-Range"], "bytes 2-5/10")
            self.assertEqual(response.read(), b"2345")

    def test_display_and_admin_entries(self) -> None:
        for path, title in (("/display", b"CORD Display"), ("/admin", b"CORD Screen Admin")):
            with urlopen(f"{self.base_url}{path}", timeout=2) as response:
                self.assertEqual(response.status, 200)
                self.assertIn(title, response.read())

        with urlopen(f"{self.base_url}/display", timeout=2) as response:
            body = response.read()
            self.assertIn(b'data-scene="artist_notice"', body)
            self.assertIn(b'data-scene="promotion"', body)
            self.assertIn(b'class="music-visual promotion-visual"', body)


if __name__ == "__main__":
    unittest.main()
