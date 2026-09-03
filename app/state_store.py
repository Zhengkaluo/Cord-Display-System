from __future__ import annotations

import copy
import hashlib
import json
import os
import platform
import queue
import threading
import time
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable


PLAYBACK_STATUSES = {"playing", "paused", "stopped"}
VISUAL_MODES = {"album_cover", "image", "video"}
DISPLAY_MODES = {"now_playing", "artist_notice", "promotion"}
CONFIG_FIELDS = {
    "source_mode",
    "transition_ms",
    "non_music_hourly_max_percent",
    "auto_insert_enabled",
    "insert_min_interval_minutes",
    "visual_mode",
    "visual_url",
}
CONTENT_FIELDS = {
    "artist_notice": {
        "eyebrow",
        "date_label",
        "time_label",
        "venue",
        "city",
        "footer",
    },
    "promotion": {
        "kind",
        "eyebrow",
        "title",
        "details",
        "callout",
        "footer",
        "image_url",
    },
}
TRACK_STRING_FIELDS = {
    "id",
    "title",
    "artist",
    "album",
    "cover_url",
    "app_name",
    "source_track_id",
    "position_accuracy",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _track_id(track: dict[str, Any]) -> str:
    raw = "|".join(
        str(track.get(key, "")).strip().lower()
        for key in ("title", "artist", "album")
    )
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def initial_state() -> dict[str, Any]:
    now = _utc_now()
    return {
        "schema_version": "1.0",
        "revision": 1,
        "updated_at": now,
        "track": {
            "id": "mock-001",
            "title": "Subterranean Homesick Alien",
            "artist": "Radiohead",
            "album": "OK Computer",
            "cover_url": "",
            "app_name": "Mock Player",
            "source_track_id": "mock-001",
            "playback_status": "playing",
            "is_playing": True,
            "position": 102.0,
            "duration": 267.0,
            "position_accuracy": "simulated",
        },
        "display": {
            "mode": "now_playing",
            "control_mode": "auto",
            "active_insert": None,
            "artist_event_id": None,
            "display_item_id": None,
            "display_item_name": "",
            "insert_source": None,
            "insert_ends_at": None,
            "insert_duration_seconds": None,
            "matched_artist": "",
            "transition": "idle",
        },
        "content": {
            "artist_notice": {
                "eyebrow": "ARTIST IN TOWN",
                "date_label": "SEP 12",
                "time_label": "20:00",
                "venue": "HOU LIVE",
                "city": "SHENZHEN",
                "footer": "UPCOMING PERFORMANCE · VERIFIED LISTING",
            },
            "promotion": {
                "kind": "bean",
                "eyebrow": "NEW BEAN · CURRENT ROTATION",
                "title": "Ethiopia\nGuji",
                "details": "JASMINE · BERGAMOT\nBLACK TEA · HONEY",
                "callout": "Available on filter",
                "footer": "ASK THE BARISTA · WHILE AVAILABLE",
                "image_url": "",
            },
        },
        "config": {
            "source_mode": "mock",
            "transition_ms": 750,
            "non_music_hourly_max_percent": 10,
            "auto_insert_enabled": True,
            "insert_min_interval_minutes": 20,
            "visual_mode": "album_cover",
            "visual_url": "",
        },
        "system": {
            "connection": "ok",
            "source": "mock",
            "platform": platform.system().lower(),
            "message": "Mock data source is active.",
            "started_at": now,
        },
    }


class StateValidationError(ValueError):
    pass


def _updated_config(config: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(patch, dict):
        raise StateValidationError("config update must be a JSON object")
    unknown = set(patch) - CONFIG_FIELDS
    if unknown:
        raise StateValidationError(f"unknown config fields: {', '.join(sorted(unknown))}")

    updated = copy.deepcopy(config)
    if "source_mode" in patch:
        value = patch["source_mode"]
        if value not in {"auto", "mock", "macos", "windows"}:
            raise StateValidationError("source_mode must be auto, mock, macos, or windows")
        updated["source_mode"] = value
    if "transition_ms" in patch:
        value = patch["transition_ms"]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 5000:
            raise StateValidationError("transition_ms must be between 0 and 5000")
        updated["transition_ms"] = int(value)
    if "non_music_hourly_max_percent" in patch:
        value = patch["non_music_hourly_max_percent"]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 20:
            raise StateValidationError("non_music_hourly_max_percent must be between 0 and 20")
        updated["non_music_hourly_max_percent"] = float(value)
    if "auto_insert_enabled" in patch:
        value = patch["auto_insert_enabled"]
        if not isinstance(value, bool):
            raise StateValidationError("auto_insert_enabled must be a boolean")
        updated["auto_insert_enabled"] = value
    if "insert_min_interval_minutes" in patch:
        value = patch["insert_min_interval_minutes"]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 <= value <= 120:
            raise StateValidationError("insert_min_interval_minutes must be between 0 and 120")
        updated["insert_min_interval_minutes"] = float(value)
    if "visual_mode" in patch:
        value = patch["visual_mode"]
        if value not in VISUAL_MODES:
            raise StateValidationError("visual_mode must be album_cover, image, or video")
        updated["visual_mode"] = value
    if "visual_url" in patch:
        value = patch["visual_url"]
        if not isinstance(value, str):
            raise StateValidationError("visual_url must be a string")
        value = value.strip()
        if len(value) > 4096:
            raise StateValidationError("visual_url is too long")
        if value and not value.startswith(("/", "http://", "https://")):
            raise StateValidationError(
                "visual_url must be an http(s) URL or a local /media/ path"
            )
        updated["visual_url"] = value
    return updated


def _updated_content(
    content: dict[str, dict[str, str]],
    section: str,
    patch: dict[str, Any],
) -> dict[str, dict[str, str]]:
    fields = CONTENT_FIELDS.get(section)
    if fields is None:
        raise StateValidationError("unknown content section")
    if not isinstance(patch, dict):
        raise StateValidationError("content update must be a JSON object")
    unknown = set(patch) - fields
    if unknown:
        raise StateValidationError(f"unknown content fields: {', '.join(sorted(unknown))}")

    updated = copy.deepcopy(content)
    section_content = updated[section]
    for field, value in patch.items():
        if not isinstance(value, str):
            raise StateValidationError(f"{field} must be a string")
        value = value.strip()
        if len(value) > 500:
            raise StateValidationError(f"{field} is too long")
        section_content[field] = value
    return updated


class StateStore:
    def __init__(
        self,
        config_path: Path | None = None,
        artist_event_matcher: Callable[[str], dict[str, Any] | None] | None = None,
        display_item_provider: Callable[[], list[dict[str, Any]]] | None = None,
    ) -> None:
        self._state = initial_state()
        self._config_path = config_path
        self._artist_event_matcher = artist_event_matcher
        self._display_item_provider = display_item_provider
        self._lock = threading.RLock()
        self._subscribers: set[queue.Queue[dict[str, Any]]] = set()
        self._insert_timer: threading.Timer | None = None
        self._last_display_item_id: int | None = None
        self._last_auto_insert_monotonic: float | None = None
        self._hourly_inserts: deque[tuple[float, float]] = deque()
        self._observed_track_identity = self._track_identity(self._state["track"])
        self._observed_playing_seconds = 0.0
        self._observed_at = time.monotonic()
        if config_path and config_path.is_file():
            try:
                payload = json.loads(config_path.read_text(encoding="utf-8"))
                persisted_config = payload.get("config", payload)
                self._state["config"] = _updated_config(
                    self._state["config"],
                    persisted_config,
                )
                if isinstance(payload.get("content"), dict):
                    content = self._state["content"]
                    for section in CONTENT_FIELDS:
                        if section in payload["content"]:
                            content = _updated_content(
                                content,
                                section,
                                payload["content"][section],
                            )
                    self._state["content"] = content
            except (OSError, json.JSONDecodeError, StateValidationError):
                pass
        self._apply_artist_match_locked()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return copy.deepcopy(self._state)

    def subscribe(self) -> queue.Queue[dict[str, Any]]:
        subscriber: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=2)
        with self._lock:
            self._subscribers.add(subscriber)
        return subscriber

    def unsubscribe(self, subscriber: queue.Queue[dict[str, Any]]) -> None:
        with self._lock:
            self._subscribers.discard(subscriber)

    def update_track(self, patch: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(patch, dict):
            raise StateValidationError("track update must be a JSON object")

        unknown = set(patch) - (
            TRACK_STRING_FIELDS
            | {"playback_status", "is_playing", "position", "duration"}
        )
        if unknown:
            raise StateValidationError(f"unknown track fields: {', '.join(sorted(unknown))}")

        with self._lock:
            previous_track = copy.deepcopy(self._state["track"])
            track = copy.deepcopy(previous_track)
            observed_now = time.monotonic()
            previous_identity = self._track_identity(previous_track)
            if self._observed_track_identity != previous_identity:
                self._observed_track_identity = previous_identity
                self._observed_playing_seconds = 0.0
            elif previous_track.get("playback_status") == "playing":
                self._observed_playing_seconds += max(0.0, observed_now - self._observed_at)
            for field in TRACK_STRING_FIELDS:
                if field in patch:
                    value = patch[field]
                    if not isinstance(value, str):
                        raise StateValidationError(f"{field} must be a string")
                    track[field] = value.strip()

            if "playback_status" in patch:
                status = patch["playback_status"]
                if status not in PLAYBACK_STATUSES:
                    raise StateValidationError("playback_status must be playing, paused, or stopped")
                track["playback_status"] = status
                track["is_playing"] = status == "playing"

            if "is_playing" in patch:
                if not isinstance(patch["is_playing"], bool):
                    raise StateValidationError("is_playing must be a boolean")
                track["is_playing"] = patch["is_playing"]
                track["playback_status"] = "playing" if patch["is_playing"] else "paused"

            for field in ("position", "duration"):
                if field in patch:
                    value = patch[field]
                    if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))):
                        raise StateValidationError(f"{field} must be a non-negative number or null")
                    if value is not None and value < 0:
                        raise StateValidationError(f"{field} must be non-negative")
                    track[field] = None if value is None else float(value)

            if track.get("position") is not None and track.get("duration") is not None:
                track["position"] = min(track["position"], track["duration"])

            identity_changed = any(field in patch for field in ("title", "artist", "album"))
            if identity_changed and "id" not in patch:
                track["id"] = _track_id(track)

            natural_end = self._is_natural_end(
                previous_track,
                track,
                self._observed_playing_seconds,
            )
            self._state["track"] = track
            current_identity = self._track_identity(track)
            if current_identity != previous_identity:
                self._observed_playing_seconds = 0.0
            self._observed_track_identity = current_identity
            self._observed_at = observed_now
            if self._state["display"].get("control_mode") == "auto":
                if self._scheduled_insert_active_locked():
                    pass
                elif natural_end and self._try_start_auto_insert_locked():
                    pass
                else:
                    self._apply_artist_match_locked()
            return self._commit_locked()

    def update_config(self, patch: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            config = _updated_config(self._state["config"], patch)
            self._state["config"] = config
            if not config["auto_insert_enabled"] and self._scheduled_insert_active_locked():
                self._cancel_insert_timer_locked()
                self._apply_artist_match_locked()
            self._persist_settings_locked()
            return self._commit_locked()

    def update_display(self, patch: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(patch, dict):
            raise StateValidationError("display update must be a JSON object")
        unknown = set(patch) - {"mode", "control_mode"}
        if unknown:
            raise StateValidationError(f"unknown display fields: {', '.join(sorted(unknown))}")
        control_mode = patch.get("control_mode", "manual")
        if control_mode not in {"auto", "manual"}:
            raise StateValidationError("control_mode must be auto or manual")
        mode = patch.get("mode")
        if control_mode == "manual" and mode not in DISPLAY_MODES:
            raise StateValidationError(
                "mode must be now_playing, artist_notice, or promotion"
            )
        with self._lock:
            self._cancel_insert_timer_locked()
            display = copy.deepcopy(self._state["display"])
            display["control_mode"] = control_mode
            if control_mode == "auto":
                self._state["display"] = display
                self._apply_artist_match_locked()
                display = self._state["display"]
            else:
                display["mode"] = mode
                display["active_insert"] = None if mode == "now_playing" else mode
                display["artist_event_id"] = None
                display["display_item_id"] = None
                display["display_item_name"] = ""
                display["insert_source"] = "manual" if mode == "promotion" else None
                display["insert_ends_at"] = None
                display["insert_duration_seconds"] = None
                display["matched_artist"] = ""
            display["transition"] = "crossfade"
            self._state["display"] = display
            return self._commit_locked()

    def preview_artist_event(self, event: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            self._cancel_insert_timer_locked()
            self._state["content"]["artist_notice"] = self._notice_from_event(event)
            display = copy.deepcopy(self._state["display"])
            display.update(
                {
                    "mode": "artist_notice",
                    "control_mode": "manual",
                    "active_insert": "artist_notice",
                    "artist_event_id": event.get("id"),
                    "display_item_id": None,
                    "display_item_name": "",
                    "insert_source": None,
                    "insert_ends_at": None,
                    "insert_duration_seconds": None,
                    "matched_artist": event.get("artist_name", ""),
                    "transition": "crossfade",
                }
            )
            self._state["display"] = display
            return self._commit_locked()

    def preview_display_item(self, item: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            self._cancel_insert_timer_locked()
            self._state["content"]["promotion"] = self._promotion_from_item(item)
            display = copy.deepcopy(self._state["display"])
            display.update(
                {
                    "mode": "promotion",
                    "control_mode": "manual",
                    "active_insert": "promotion",
                    "artist_event_id": None,
                    "display_item_id": item.get("id"),
                    "display_item_name": str(item.get("name") or ""),
                    "insert_source": "manual",
                    "insert_ends_at": None,
                    "insert_duration_seconds": None,
                    "matched_artist": "",
                    "transition": "crossfade",
                }
            )
            self._state["display"] = display
            return self._commit_locked()

    def finish_scheduled_insert(self) -> dict[str, Any]:
        with self._lock:
            if not self._scheduled_insert_active_locked():
                return copy.deepcopy(self._state)
            self._cancel_insert_timer_locked()
            self._apply_artist_match_locked()
            self._state["display"]["transition"] = "crossfade"
            return self._commit_locked()

    def close(self) -> None:
        with self._lock:
            self._cancel_insert_timer_locked()

    def refresh_artist_match(self) -> dict[str, Any]:
        with self._lock:
            if self._state["display"].get("control_mode") != "auto":
                return copy.deepcopy(self._state)
            if self._scheduled_insert_active_locked():
                return copy.deepcopy(self._state)
            before = copy.deepcopy(self._state["display"])
            self._apply_artist_match_locked()
            if self._state["display"] == before:
                return copy.deepcopy(self._state)
            return self._commit_locked()

    def update_content(self, section: str, patch: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            self._state["content"] = _updated_content(
                self._state["content"],
                section,
                patch,
            )
            self._persist_settings_locked()
            return self._commit_locked()

    def _persist_settings_locked(self) -> None:
        if not self._config_path:
            return
        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._config_path.with_suffix(self._config_path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(
                {
                    "config": self._state["config"],
                    "content": self._state["content"],
                },
                ensure_ascii=False,
                indent=2,
            ) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, self._config_path)

    @staticmethod
    def _promotion_from_item(item: dict[str, Any]) -> dict[str, str]:
        return {
            "kind": str(item.get("content_type") or "bean"),
            "eyebrow": str(item.get("eyebrow") or ""),
            "title": str(item.get("title") or ""),
            "details": str(item.get("details") or ""),
            "callout": str(item.get("callout") or ""),
            "footer": str(item.get("footer") or ""),
            "image_url": str(item.get("image_url") or ""),
        }

    @staticmethod
    def _track_identity(track: dict[str, Any]) -> tuple[str, str, str, str]:
        return tuple(
            str(track.get(field) or "").strip().casefold()
            for field in ("source_track_id", "title", "artist", "album")
        )

    @classmethod
    def _is_natural_end(
        cls,
        previous: dict[str, Any],
        current: dict[str, Any],
        observed_playing_seconds: float = 0,
    ) -> bool:
        if previous.get("playback_status") != "playing":
            return False
        position = previous.get("position")
        duration = previous.get("duration")
        if not isinstance(duration, (int, float)):
            return False
        if duration <= 0:
            return False
        near_reported_end = (
            isinstance(position, (int, float)) and duration - position <= 6
        )
        near_estimated_end = (
            position is None and observed_playing_seconds >= max(0, duration - 6)
        )
        if not near_reported_end and not near_estimated_end:
            return False

        changed_track = cls._track_identity(previous) != cls._track_identity(current)
        stopped = current.get("playback_status") == "stopped"
        restarted = (
            current.get("playback_status") == "playing"
            and isinstance(current.get("position"), (int, float))
            and current["position"] + 6 < position
        )
        return changed_track or stopped or restarted

    def _scheduled_insert_active_locked(self) -> bool:
        display = self._state["display"]
        return (
            display.get("control_mode") == "auto"
            and display.get("mode") == "promotion"
            and display.get("insert_source") == "scheduler"
        )

    def _try_start_auto_insert_locked(self) -> bool:
        config = self._state["config"]
        if not config.get("auto_insert_enabled") or not self._display_item_provider:
            return False

        now = time.monotonic()
        minimum_interval = float(config.get("insert_min_interval_minutes", 20)) * 60
        if (
            self._last_auto_insert_monotonic is not None
            and now - self._last_auto_insert_monotonic < minimum_interval
        ):
            return False

        items = self._display_item_provider()
        if not items:
            return False
        item_ids = [int(item["id"]) for item in items]
        if self._last_display_item_id in item_ids:
            index = (item_ids.index(self._last_display_item_id) + 1) % len(items)
        else:
            index = 0
        item = items[index]
        duration = int(item.get("display_seconds") or 10)

        while self._hourly_inserts and now - self._hourly_inserts[0][0] >= 3600:
            self._hourly_inserts.popleft()
        used_seconds = sum(entry[1] for entry in self._hourly_inserts)
        hourly_budget = float(config.get("non_music_hourly_max_percent", 10)) * 36
        if hourly_budget <= 0 or used_seconds + duration > hourly_budget:
            return False

        self._state["content"]["promotion"] = self._promotion_from_item(item)
        self._state["display"].update(
            {
                "mode": "promotion",
                "control_mode": "auto",
                "active_insert": "promotion",
                "artist_event_id": None,
                "display_item_id": item.get("id"),
                "display_item_name": str(item.get("name") or ""),
                "insert_source": "scheduler",
                "insert_ends_at": (
                    datetime.now(timezone.utc) + timedelta(seconds=duration)
                ).isoformat(timespec="seconds"),
                "insert_duration_seconds": duration,
                "matched_artist": "",
                "transition": "crossfade",
            }
        )
        self._last_display_item_id = int(item["id"])
        self._last_auto_insert_monotonic = now
        self._hourly_inserts.append((now, duration))
        timer = threading.Timer(duration, self.finish_scheduled_insert)
        timer.daemon = True
        self._insert_timer = timer
        timer.start()
        return True

    def _cancel_insert_timer_locked(self) -> None:
        if self._insert_timer:
            self._insert_timer.cancel()
            self._insert_timer = None

    @staticmethod
    def _notice_from_event(event: dict[str, Any]) -> dict[str, str]:
        return {
            "eyebrow": str(event.get("eyebrow") or "ARTIST IN TOWN"),
            "date_label": str(event.get("date_label") or "DATE TBA"),
            "time_label": str(event.get("time_label") or "TBA"),
            "venue": str(event.get("venue") or "VENUE TBA"),
            "city": str(event.get("city") or "CITY TBA"),
            "footer": str(event.get("footer") or "UPCOMING PERFORMANCE · VERIFIED LISTING"),
        }

    def _apply_artist_match_locked(self) -> None:
        display = copy.deepcopy(self._state["display"])
        display["control_mode"] = "auto"
        track = self._state["track"]
        event = None
        if (
            self._artist_event_matcher
            and track.get("playback_status") != "stopped"
            and track.get("artist")
        ):
            event = self._artist_event_matcher(str(track["artist"]))
        if event:
            self._state["content"]["artist_notice"] = self._notice_from_event(event)
            display.update(
                {
                    "mode": "artist_notice",
                    "active_insert": "artist_notice",
                    "artist_event_id": event.get("id"),
                    "display_item_id": None,
                    "display_item_name": "",
                    "insert_source": None,
                    "insert_ends_at": None,
                    "insert_duration_seconds": None,
                    "matched_artist": event.get("artist_name", ""),
                    "transition": "crossfade",
                }
            )
        else:
            display.update(
                {
                    "mode": "now_playing",
                    "active_insert": None,
                    "artist_event_id": None,
                    "display_item_id": None,
                    "display_item_name": "",
                    "insert_source": None,
                    "insert_ends_at": None,
                    "insert_duration_seconds": None,
                    "matched_artist": "",
                    "transition": "crossfade",
                }
            )
        self._state["display"] = display

    def prepare_live_source(self) -> dict[str, Any]:
        return self.update_track(
            {
                "title": "No active track",
                "artist": "CORD",
                "album": "Waiting for a media player",
                "cover_url": "",
                "app_name": "",
                "source_track_id": "",
                "playback_status": "stopped",
                "position": None,
                "duration": None,
                "position_accuracy": "unavailable",
            }
        )

    def update_system(
        self,
        *,
        source: str,
        connection: str,
        message: str = "",
    ) -> dict[str, Any]:
        with self._lock:
            system = copy.deepcopy(self._state["system"])
            next_values = {
                "source": source,
                "connection": connection,
                "message": message,
            }
            if all(system.get(key) == value for key, value in next_values.items()):
                return copy.deepcopy(self._state)
            system.update(next_values)
            self._state["system"] = system
            return self._commit_locked()

    def _commit_locked(self) -> dict[str, Any]:
        self._state["revision"] += 1
        self._state["updated_at"] = _utc_now()
        snapshot = copy.deepcopy(self._state)
        stale: list[queue.Queue[dict[str, Any]]] = []
        for subscriber in self._subscribers:
            try:
                if subscriber.full():
                    try:
                        subscriber.get_nowait()
                    except queue.Empty:
                        pass
                subscriber.put_nowait(snapshot)
            except queue.Full:
                stale.append(subscriber)
        for subscriber in stale:
            self._subscribers.discard(subscriber)
        return snapshot
