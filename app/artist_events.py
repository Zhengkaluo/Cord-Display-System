from __future__ import annotations

import json
import re
import sqlite3
import unicodedata
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


EVENT_FIELDS = {
    "artist_name",
    "aliases",
    "event_date",
    "date_label",
    "time_label",
    "venue",
    "city",
    "active_from",
    "active_until",
    "eyebrow",
    "footer",
    "source_note",
    "enabled",
    "priority",
}
TEXT_FIELDS = EVENT_FIELDS - {"aliases", "enabled", "priority"}
MONTH_LABELS = (
    "JAN",
    "FEB",
    "MAR",
    "APR",
    "MAY",
    "JUN",
    "JUL",
    "AUG",
    "SEP",
    "OCT",
    "NOV",
    "DEC",
)


class ArtistEventValidationError(ValueError):
    pass


def normalize_artist_name(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold().strip()
    value = value.replace("’", "'")
    return " ".join(re.sub(r"[^\w]+", " ", value, flags=re.UNICODE).split())


def artist_name_candidates(value: str) -> set[str]:
    full = normalize_artist_name(value)
    if not full:
        return set()
    pieces = re.split(
        r"\s+(?:feat(?:uring)?|ft)\.?\s+|\s+[x×]\s+|[,&/+、，;；]",
        unicodedata.normalize("NFKC", value),
        flags=re.IGNORECASE,
    )
    return {full} | {name for piece in pieces if (name := normalize_artist_name(piece))}


def _date_value(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise ArtistEventValidationError(f"{field} must be a string")
    value = value.strip()
    if not value:
        return ""
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise ArtistEventValidationError(f"{field} must use YYYY-MM-DD") from exc
    return value


def _date_label(event_date: str) -> str:
    parsed = date.fromisoformat(event_date)
    return f"{MONTH_LABELS[parsed.month - 1]} {parsed.day:02d}"


def _aliases(value: Any) -> list[str]:
    if isinstance(value, str):
        values = re.split(r"[,，\n]+", value)
    elif isinstance(value, list):
        values = value
    else:
        raise ArtistEventValidationError("aliases must be a string or list")
    cleaned: list[str] = []
    seen: set[str] = set()
    for item in values:
        if not isinstance(item, str):
            raise ArtistEventValidationError("each alias must be a string")
        item = item.strip()
        normalized = normalize_artist_name(item)
        if item and normalized not in seen:
            cleaned.append(item)
            seen.add(normalized)
    return cleaned


def _validated_event(payload: dict[str, Any], existing: dict[str, Any] | None = None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ArtistEventValidationError("artist event must be a JSON object")
    unknown = set(payload) - EVENT_FIELDS
    if unknown:
        raise ArtistEventValidationError(f"unknown artist event fields: {', '.join(sorted(unknown))}")

    event = {
        "artist_name": "",
        "aliases": [],
        "event_date": "",
        "date_label": "",
        "time_label": "",
        "venue": "",
        "city": "",
        "active_from": "",
        "active_until": "",
        "eyebrow": "ARTIST IN TOWN",
        "footer": "UPCOMING PERFORMANCE · VERIFIED LISTING",
        "source_note": "",
        "enabled": True,
        "priority": 0,
    }
    if existing:
        event.update({key: existing[key] for key in EVENT_FIELDS if key in existing})

    for field in TEXT_FIELDS:
        if field not in payload:
            continue
        value = payload[field]
        if not isinstance(value, str):
            raise ArtistEventValidationError(f"{field} must be a string")
        value = value.strip()
        if len(value) > 500:
            raise ArtistEventValidationError(f"{field} is too long")
        event[field] = value
    if "aliases" in payload:
        event["aliases"] = _aliases(payload["aliases"])
    if "enabled" in payload:
        if not isinstance(payload["enabled"], bool):
            raise ArtistEventValidationError("enabled must be a boolean")
        event["enabled"] = payload["enabled"]
    if "priority" in payload:
        value = payload["priority"]
        if isinstance(value, bool) or not isinstance(value, int) or not -100 <= value <= 100:
            raise ArtistEventValidationError("priority must be an integer between -100 and 100")
        event["priority"] = value

    event["event_date"] = _date_value(event["event_date"], "event_date")
    event["active_from"] = _date_value(event["active_from"], "active_from")
    event["active_until"] = _date_value(event["active_until"], "active_until")
    if not event["artist_name"]:
        raise ArtistEventValidationError("artist_name is required")
    if not event["event_date"]:
        raise ArtistEventValidationError("event_date is required")
    if event["active_from"] and event["active_until"] and event["active_from"] > event["active_until"]:
        raise ArtistEventValidationError("active_from cannot be later than active_until")
    if not event["date_label"]:
        event["date_label"] = _date_label(event["event_date"])
    return event


class ArtistEventStore:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS artist_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    artist_name TEXT NOT NULL,
                    aliases_json TEXT NOT NULL DEFAULT '[]',
                    event_date TEXT NOT NULL,
                    date_label TEXT NOT NULL,
                    time_label TEXT NOT NULL DEFAULT '',
                    venue TEXT NOT NULL DEFAULT '',
                    city TEXT NOT NULL DEFAULT '',
                    active_from TEXT NOT NULL DEFAULT '',
                    active_until TEXT NOT NULL DEFAULT '',
                    eyebrow TEXT NOT NULL DEFAULT 'ARTIST IN TOWN',
                    footer TEXT NOT NULL DEFAULT 'UPCOMING PERFORMANCE · VERIFIED LISTING',
                    source_note TEXT NOT NULL DEFAULT '',
                    enabled INTEGER NOT NULL DEFAULT 1,
                    priority INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS artist_events_active_idx ON artist_events(enabled, event_date, priority)"
            )

    def list(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM artist_events ORDER BY enabled DESC, event_date ASC, priority DESC, id ASC"
            ).fetchall()
        return [self._public(row) for row in rows]

    def get(self, event_id: int) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM artist_events WHERE id = ?",
                (event_id,),
            ).fetchone()
        return self._public(row) if row else None

    def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        event = _validated_event(payload)
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        values = self._database_values(event)
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO artist_events (
                    artist_name, aliases_json, event_date, date_label, time_label,
                    venue, city, active_from, active_until, eyebrow, footer,
                    source_note, enabled, priority, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (*values, now, now),
            )
            event_id = int(cursor.lastrowid)
        return self.get(event_id) or {}

    def update(self, event_id: int, payload: dict[str, Any]) -> dict[str, Any] | None:
        existing = self.get(event_id)
        if not existing:
            return None
        event = _validated_event(payload, existing)
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        values = self._database_values(event)
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE artist_events SET
                    artist_name = ?, aliases_json = ?, event_date = ?, date_label = ?,
                    time_label = ?, venue = ?, city = ?, active_from = ?, active_until = ?,
                    eyebrow = ?, footer = ?, source_note = ?, enabled = ?, priority = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (*values, now, event_id),
            )
        return self.get(event_id)

    def delete(self, event_id: int) -> bool:
        with self._connect() as connection:
            cursor = connection.execute("DELETE FROM artist_events WHERE id = ?", (event_id,))
            return cursor.rowcount > 0

    def find_match(self, artist: str, today: date | None = None) -> dict[str, Any] | None:
        candidates = artist_name_candidates(artist)
        if not candidates:
            return None
        today_value = (today or date.today()).isoformat()
        matches: list[dict[str, Any]] = []
        for event in self.list():
            if not event["enabled"]:
                continue
            if event["active_from"] and today_value < event["active_from"]:
                continue
            expires_on = event["active_until"] or event["event_date"]
            if expires_on and today_value > expires_on:
                continue
            names = {normalize_artist_name(event["artist_name"])}
            names.update(normalize_artist_name(alias) for alias in event["aliases"])
            if candidates.isdisjoint(names):
                continue
            matches.append(event)
        if not matches:
            return None
        matches.sort(key=lambda item: (-item["priority"], item["event_date"], item["id"]))
        return matches[0]

    @staticmethod
    def _database_values(event: dict[str, Any]) -> tuple[Any, ...]:
        return (
            event["artist_name"],
            json.dumps(event["aliases"], ensure_ascii=False),
            event["event_date"],
            event["date_label"],
            event["time_label"],
            event["venue"],
            event["city"],
            event["active_from"],
            event["active_until"],
            event["eyebrow"],
            event["footer"],
            event["source_note"],
            1 if event["enabled"] else 0,
            event["priority"],
        )

    @staticmethod
    def _public(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": int(row["id"]),
            "artist_name": row["artist_name"],
            "aliases": json.loads(row["aliases_json"]),
            "event_date": row["event_date"],
            "date_label": row["date_label"],
            "time_label": row["time_label"],
            "venue": row["venue"],
            "city": row["city"],
            "active_from": row["active_from"],
            "active_until": row["active_until"],
            "eyebrow": row["eyebrow"],
            "footer": row["footer"],
            "source_note": row["source_note"],
            "enabled": bool(row["enabled"]),
            "priority": int(row["priority"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
