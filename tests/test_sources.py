from __future__ import annotations

import unittest

from app.sources.factory import build_source
from app.sources.base import SourceResult
from app.sources.macos import MacOSNowPlayingSource, normalize_mediaremote_payload
from app.sources.mock import MockSource
from app.sources.windows import normalize_windows_payload


class SourceTestCase(unittest.TestCase):
    def test_mock_source_can_be_selected_on_any_platform(self) -> None:
        self.assertIsInstance(build_source("mock", system="Darwin"), MockSource)
        self.assertIsInstance(build_source("mock", system="Windows"), MockSource)

    def test_auto_falls_back_to_mock_on_unknown_platform(self) -> None:
        self.assertIsInstance(build_source("auto", system="Linux"), MockSource)

    def test_mediaremote_payload_normalization_for_qq_music(self) -> None:
        track = normalize_mediaremote_payload(
            {
                "title": " Test ",
                "artist": " Artist ",
                "album": " Album ",
                "clientBundleIdentifier": "com.tencent.QQMusicMac",
                "playing": True,
                "playbackRate": 1,
                "elapsedTime": "12.5",
                "duration": 180,
                "artworkData": "/9j/",
                "artworkMIMEType": None,
            }
        )
        self.assertEqual(track["title"], "Test")
        self.assertEqual(track["app_name"], "QQ音乐")
        self.assertEqual(track["playback_status"], "playing")
        self.assertEqual(track["position"], 12.5)
        self.assertEqual(track["duration"], 180.0)
        self.assertTrue(track["cover_url"].startswith("data:image/jpeg;base64,"))

    def test_mediaremote_prefers_explicit_playing_flag(self) -> None:
        track = normalize_mediaremote_payload(
            {
                "title": "Paused track",
                "clientBundleIdentifier": "com.tencent.QQMusicMac",
                "playing": False,
                "playbackRate": 1,
            }
        )
        self.assertEqual(track["playback_status"], "paused")
        self.assertFalse(track["is_playing"])

    def test_mediaremote_falls_back_to_applescript(self) -> None:
        class FakeSource:
            def __init__(self, name: str, result: SourceResult) -> None:
                self.name = name
                self.result = result

            def poll(self) -> SourceResult:
                return self.result

        mediaremote = FakeSource(
            "macos-mediaremote",
            SourceResult(connection="tool_missing", message="missing"),
        )
        applescript = FakeSource(
            "macos-applescript",
            SourceResult(
                connection="ok",
                message="Reading Apple Music via AppleScript.",
                track={"title": "Fallback track"},
            ),
        )
        result = MacOSNowPlayingSource(mediaremote, applescript).poll()
        self.assertEqual(result.connection, "ok")
        self.assertEqual(result.track, {"title": "Fallback track"})
        self.assertIn("MediaRemote: tool_missing", result.message)

    def test_inactive_mediaremote_stops_last_track(self) -> None:
        class SequenceSource:
            name = "macos-mediaremote"

            def __init__(self) -> None:
                self.results = [
                    SourceResult(
                        connection="ok",
                        track={
                            "title": "Last track",
                            "playback_status": "playing",
                            "is_playing": True,
                            "position": 10.0,
                            "position_accuracy": "reported",
                        },
                    ),
                    SourceResult(connection="waiting", message="inactive"),
                ]

            def poll(self) -> SourceResult:
                return self.results.pop(0)

        class WaitingSource:
            name = "macos-applescript"

            def poll(self) -> SourceResult:
                return SourceResult(connection="waiting", message="inactive")

        source = MacOSNowPlayingSource(SequenceSource(), WaitingSource())
        self.assertTrue(source.poll().track["is_playing"])
        inactive = source.poll()
        self.assertEqual(inactive.connection, "waiting")
        self.assertEqual(inactive.track["playback_status"], "stopped")
        self.assertFalse(inactive.track["is_playing"])
        self.assertIsNone(inactive.track["position"])

    def test_windows_payload_normalization_without_timeline(self) -> None:
        track = normalize_windows_payload(
            {
                "title": "Windows Track",
                "artist": "Artist",
                "album_title": "Album",
                "app_name": "Spotify.exe",
                "playback_status_code": 4,
                "thumbnail_base64": "iVBORw0KGgo=",
            }
        )
        self.assertEqual(track["playback_status"], "playing")
        self.assertTrue(track["is_playing"])
        self.assertIsNone(track["position"])
        self.assertIsNone(track["duration"])
        self.assertTrue(track["cover_url"].startswith("data:image/png;base64,"))

    def test_windows_payload_normalization_with_smtc_timeline(self) -> None:
        track = normalize_windows_payload(
            {
                "title": "Windows Track",
                "artist": "Artist",
                "playback_status_code": 4,
                "position": 172.5,
                "duration": 180,
            }
        )
        self.assertEqual(track["position"], 172.5)
        self.assertEqual(track["duration"], 180.0)


if __name__ == "__main__":
    unittest.main()
