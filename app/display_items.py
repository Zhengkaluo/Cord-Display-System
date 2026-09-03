from __future__ import annotations

import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


ITEM_FIELDS = {
    "name",
    "content_type",
    "eyebrow",
    "title",
    "details",
    "callout",
    "footer",
    "image_url",
    "active_from",
    "active_until",
    "enabled",
    "priority",
    "display_seconds",
}
TEXT_FIELDS = ITEM_FIELDS - {"enabled", "priority", "display_seconds"}
CONTENT_TYPES = {"bean", "event"}


class DisplayItemValidationError(ValueError):
    pass


def _date_value(value: Any, field: str) -> str:
    if not isinstance(value, str):
        raise DisplayItemValidationError(f"{field} must be a string")
    value = value.strip()
    if not value:
        return ""
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise DisplayItemValidationError(f"{field} must use YYYY-MM-DD") from exc
    return value


def _validated_item(payload: dict[str, Any], existing: dict[str, Any] | None = None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise DisplayItemValidationError("display item must be a JSON object")
    unknown = set(payload) - ITEM_FIELDS
    if unknown:
        raise DisplayItemValidationError(f"unknown display item fields: {', '.join(sorted(unknown))}")

    item = {
        "name": "",
        "content_type": "bean",
        "eyebrow": "NEW BEAN · CURRENT ROTATION",
        "title": "",
        "details": "",
        "callout": "",
        "footer": "ASK THE BARISTA · WHILE AVAILABLE",
        "image_url": "",
        "active_from": "",
        "active_until": "",
        "enabled": True,
        "priority": 0,
        "display_seconds": 10,
    }
    if existing:
        item.update({key: existing[key] for key in ITEM_FIELDS if key in existing})

    for field in TEXT_FIELDS:
        if field not in payload:
            continue
        value = payload[field]
        if not isinstance(value, str):
            raise DisplayItemValidationError(f"{field} must be a string")
        value = value.strip()
        max_length = 4096 if field == "image_url" else 1000
        if len(value) > max_length:
            raise DisplayItemValidationError(f"{field} is too long")
        item[field] = value
    if item["content_type"] not in CONTENT_TYPES:
        raise DisplayItemValidationError("content_type must be bean or event")
    if item["image_url"] and not item["image_url"].startswith(("/media/", "http://", "https://")):
        raise DisplayItemValidationError(
            "image_url must be an http(s) URL or a local /media/ path"
        )
    if "enabled" in payload:
        if not isinstance(payload["enabled"], bool):
            raise DisplayItemValidationError("enabled must be a boolean")
        item["enabled"] = payload["enabled"]
    if "priority" in payload:
        value = payload["priority"]
        if isinstance(value, bool) or not isinstance(value, int) or not -100 <= value <= 100:
            raise DisplayItemValidationError("priority must be an integer between -100 and 100")
        item["priority"] = value
    if "display_seconds" in payload:
        value = payload["display_seconds"]
        if isinstance(value, bool) or not isinstance(value, int) or not 3 <= value <= 120:
            raise DisplayItemValidationError("display_seconds must be an integer between 3 and 120")
        item["display_seconds"] = value

    item["active_from"] = _date_value(item["active_from"], "active_from")
    item["active_until"] = _date_value(item["active_until"], "active_until")
    if item["active_from"] and item["active_until"] and item["active_from"] > item["active_until"]:
        raise DisplayItemValidationError("active_from cannot be later than active_until")
    if not item["name"]:
        raise DisplayItemValidationError("name is required")
    if not item["title"] and not item["image_url"]:
        raise DisplayItemValidationError("title or image_url is required")
    return item


class DisplayItemStore:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS display_items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    content_type TEXT NOT NULL,
                    eyebrow TEXT NOT NULL DEFAULT '',
                    title TEXT NOT NULL,
                    details TEXT NOT NULL DEFAULT '',
                    callout TEXT NOT NULL DEFAULT '',
                    footer TEXT NOT NULL DEFAULT '',
                    image_url TEXT NOT NULL DEFAULT '',
                    active_from TEXT NOT NULL DEFAULT '',
                    active_until TEXT NOT NULL DEFAULT '',
                    enabled INTEGER NOT NULL DEFAULT 1,
                    priority INTEGER NOT NULL DEFAULT 0,
                    display_seconds INTEGER NOT NULL DEFAULT 10,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            columns = {
                row["name"]
                for row in connection.execute("PRAGMA table_info(display_items)").fetchall()
            }
            if "image_url" not in columns:
                connection.execute(
                    "ALTER TABLE display_items ADD COLUMN image_url TEXT NOT NULL DEFAULT ''"
                )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS display_items_active_idx ON display_items(enabled, active_from, active_until, priority)"
            )
            connection.execute(
                "CREATE TABLE IF NOT EXISTS app_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
            )

    def list(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM display_items ORDER BY enabled DESC, priority DESC, id ASC"
            ).fetchall()
        return [self._public(row) for row in rows]

    def list_eligible(self, today: date | None = None) -> list[dict[str, Any]]:
        today_value = (today or date.today()).isoformat()
        return [
            item
            for item in self.list()
            if item["enabled"]
            and (not item["active_from"] or today_value >= item["active_from"])
            and (not item["active_until"] or today_value <= item["active_until"])
        ]

    def get(self, item_id: int) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM display_items WHERE id = ?", (item_id,)).fetchone()
        return self._public(row) if row else None

    def create(self, payload: dict[str, Any]) -> dict[str, Any]:
        item = _validated_item(payload)
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO display_items (
                    name, content_type, eyebrow, title, details, callout, footer, image_url,
                    active_from, active_until, enabled, priority, display_seconds,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (*self._database_values(item), now, now),
            )
            item_id = int(cursor.lastrowid)
        return self.get(item_id) or {}

    def update(self, item_id: int, payload: dict[str, Any]) -> dict[str, Any] | None:
        existing = self.get(item_id)
        if not existing:
            return None
        item = _validated_item(payload, existing)
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE display_items SET
                    name = ?, content_type = ?, eyebrow = ?, title = ?, details = ?,
                    callout = ?, footer = ?, image_url = ?, active_from = ?, active_until = ?,
                    enabled = ?, priority = ?, display_seconds = ?, updated_at = ?
                WHERE id = ?
                """,
                (*self._database_values(item), now, item_id),
            )
        return self.get(item_id)

    def delete(self, item_id: int) -> bool:
        with self._connect() as connection:
            cursor = connection.execute("DELETE FROM display_items WHERE id = ?", (item_id,))
            return cursor.rowcount > 0

    def migrate_legacy_promotion(self, content: dict[str, Any]) -> dict[str, Any] | None:
        migration_key = "legacy_promotion_migrated_v1"
        with self._connect() as connection:
            already_migrated = connection.execute(
                "SELECT 1 FROM app_meta WHERE key = ?",
                (migration_key,),
            ).fetchone()
            if already_migrated:
                return None
            has_items = connection.execute("SELECT 1 FROM display_items LIMIT 1").fetchone()

        created = None
        title = str(content.get("title") or "").strip()
        if not has_items and title:
            name = " ".join(title.split())[:120]
            created = self.create(
                {
                    "name": name,
                    "content_type": content.get("kind") if content.get("kind") in CONTENT_TYPES else "bean",
                    "eyebrow": str(content.get("eyebrow") or ""),
                    "title": title,
                    "details": str(content.get("details") or ""),
                    "callout": str(content.get("callout") or ""),
                    "footer": str(content.get("footer") or ""),
                    "image_url": str(content.get("image_url") or ""),
                }
            )
        with self._connect() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO app_meta(key, value) VALUES (?, ?)",
                (migration_key, datetime.now(timezone.utc).isoformat(timespec="seconds")),
            )
        return created

    @staticmethod
    def _database_values(item: dict[str, Any]) -> tuple[Any, ...]:
        return (
            item["name"],
            item["content_type"],
            item["eyebrow"],
            item["title"],
            item["details"],
            item["callout"],
            item["footer"],
            item["image_url"],
            item["active_from"],
            item["active_until"],
            1 if item["enabled"] else 0,
            item["priority"],
            item["display_seconds"],
        )

    @staticmethod
    def _public(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": int(row["id"]),
            "name": row["name"],
            "content_type": row["content_type"],
            "eyebrow": row["eyebrow"],
            "title": row["title"],
            "details": row["details"],
            "callout": row["callout"],
            "footer": row["footer"],
            "image_url": row["image_url"],
            "active_from": row["active_from"],
            "active_until": row["active_until"],
            "enabled": bool(row["enabled"]),
            "priority": int(row["priority"]),
            "display_seconds": int(row["display_seconds"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
