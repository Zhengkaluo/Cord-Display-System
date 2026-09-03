from __future__ import annotations

import base64
import json
import os
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any

from .base import SourceResult


DEFAULT_SOURCE_PATH = (
    Path(__file__).resolve().parents[3]
    / "Music-Player-Investigation"
    / "get_music_powershell.py"
)


class WindowsSMTCSource:
    name = "windows-smtc"

    def __init__(self, source_path: Path | None = None, timeout: float = 15.0) -> None:
        configured = os.environ.get("CORD_WINDOWS_SOURCE")
        self.source_path = Path(configured) if configured else (source_path or DEFAULT_SOURCE_PATH)
        self.timeout = timeout

    def poll(self) -> SourceResult:
        if platform.system() != "Windows":
            return SourceResult(connection="unsupported", message="Windows SMTC source requires Windows.")
        if not self.source_path.is_file():
            return SourceResult(
                connection="missing_source",
                message=f"SMTC source not found: {self.source_path}",
            )

        try:
            result = subprocess.run(
                [sys.executable, str(self.source_path), "--json", "--thumbnail"],
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return SourceResult(connection="error", message=f"Windows SMTC source failed: {exc}")

        if result.returncode != 0:
            detail = result.stderr.strip() or "SMTC source returned an error"
            return SourceResult(connection="error", message=detail)

        try:
            payload = json.loads(result.stdout.strip() or "{}")
        except json.JSONDecodeError:
            return SourceResult(connection="error", message="Windows SMTC source returned invalid JSON.")

        if payload.get("status") != "success" or not payload.get("title"):
            return SourceResult(
                connection="waiting",
                message=str(payload.get("message") or "No active Windows media session."),
            )
        track = normalize_windows_payload(payload)
        return SourceResult(connection="ok", message=f"Reading {track['app_name']} via Windows SMTC.", track=track)


def normalize_windows_payload(payload: dict[str, Any]) -> dict[str, Any]:
    status = _normalize_status(payload)
    thumbnail = payload.get("thumbnail_base64")
    cover_url = ""
    if isinstance(thumbnail, str) and thumbnail:
        try:
            raw_thumbnail = base64.b64decode(thumbnail, validate=True)
            mime = _image_mime(raw_thumbnail)
            if mime:
                cover_url = f"data:{mime};base64,{thumbnail}"
        except ValueError:
            cover_url = ""

    return {
        "title": str(payload.get("title") or "").strip(),
        "artist": str(payload.get("artist") or "").strip(),
        "album": str(payload.get("album_title") or "").strip(),
        "cover_url": cover_url,
        "app_name": str(payload.get("app_name") or "Windows media").strip(),
        "playback_status": status,
        "is_playing": status == "playing",
        "position": _non_negative_number(payload.get("position")),
        "duration": _non_negative_number(payload.get("duration")),
    }


def _normalize_status(payload: dict[str, Any]) -> str:
    status = str(payload.get("playback_status") or "").lower()
    if "play" in status or payload.get("playback_status_code") == 4:
        return "playing"
    if "pause" in status:
        return "paused"
    return "stopped"


def _image_mime(data: bytes) -> str | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def _non_negative_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None
