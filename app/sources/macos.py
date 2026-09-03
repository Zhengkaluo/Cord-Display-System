from __future__ import annotations

import base64
import json
import os
import platform
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from .base import SourceResult, TrackSource


PROJECT_ROOT = Path(__file__).resolve().parents[2]
LOCAL_NOWPLAYING_CLI = (
    PROJECT_ROOT / ".tools" / "nowplaying-cli" / "bin" / "nowplaying-cli"
)
MEDIAREMOTE_PROPERTIES = (
    "title",
    "artist",
    "album",
    "duration",
    "elapsedTime",
    "playing",
    "playbackRate",
    "clientBundleIdentifier",
    "uniqueIdentifier",
    "artworkData",
    "artworkMIMEType",
)

BUNDLE_NAMES = {
    "com.apple.music": "Apple Music",
    "com.spotify.client": "Spotify",
    "com.tencent.qqmusicmac": "QQ音乐",
    "com.netease.163music": "网易云音乐",
}


JXA_SCRIPT = r"""
ObjC.import('Foundation');

function value(callable, fallback) {
  try {
    const result = callable();
    return result === undefined || result === null ? fallback : result;
  } catch (_) {
    return fallback;
  }
}

function normalizedState(raw) {
  const state = String(raw || '').toLowerCase();
  if (state.includes('play')) return 'playing';
  if (state.includes('pause')) return 'paused';
  return 'stopped';
}

function spotifyTrack() {
  try {
    const app = Application('Spotify');
    if (!app.running()) return null;
    const state = normalizedState(value(() => app.playerState(), 'stopped'));
    if (state === 'stopped') return null;
    const track = app.currentTrack();
    return {
      title: String(value(() => track.name(), '')),
      artist: String(value(() => track.artist(), '')),
      album: String(value(() => track.album(), '')),
      cover_url: String(value(() => track.artworkUrl(), '')),
      app_name: 'Spotify',
      source_track_id: String(value(() => track.id(), '')),
      playback_status: state,
      is_playing: state === 'playing',
      position: Number(value(() => app.playerPosition(), 0)),
      duration: Number(value(() => track.duration(), 0)) / 1000,
      position_accuracy: 'reported'
    };
  } catch (_) {
    return null;
  }
}

function musicTrack() {
  try {
    const app = Application('Music');
    if (!app.running()) return null;
    const state = normalizedState(value(() => app.playerState(), 'stopped'));
    if (state === 'stopped') return null;
    const track = app.currentTrack();
    return {
      title: String(value(() => track.name(), '')),
      artist: String(value(() => track.artist(), '')),
      album: String(value(() => track.album(), '')),
      cover_url: '',
      app_name: 'Apple Music',
      source_track_id: String(value(() => track.persistentID(), '')),
      playback_status: state,
      is_playing: state === 'playing',
      position: Number(value(() => app.playerPosition(), 0)),
      duration: Number(value(() => track.duration(), 0)),
      position_accuracy: 'reported'
    };
  } catch (_) {
    return null;
  }
}

const candidates = [spotifyTrack(), musicTrack()].filter(Boolean);
const active = candidates.find(item => item.is_playing) || candidates[0] || null;
JSON.stringify({ track: active });
"""


class MacOSMediaRemoteSource:
    name = "macos-mediaremote"

    def __init__(self, cli_path: Path | None = None, timeout: float = 8.0) -> None:
        self.cli_path = cli_path or find_nowplaying_cli()
        self.timeout = timeout
        self._last_identity = ""
        self._last_elapsed: float | None = None
        self._last_elapsed_at = 0.0
        self._timeline_reliable: bool | None = None

    def poll(self) -> SourceResult:
        if platform.system() != "Darwin":
            return SourceResult(connection="unsupported", message="MediaRemote requires macOS.")
        if not self.cli_path:
            return SourceResult(
                connection="tool_missing",
                message="Project-local nowplaying-cli is not installed.",
            )

        try:
            result = subprocess.run(
                [str(self.cli_path), "get", "--json", *MEDIAREMOTE_PROPERTIES],
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return SourceResult(connection="error", message=f"MediaRemote failed: {exc}")

        if result.returncode != 0:
            detail = result.stderr.strip() or "nowplaying-cli returned an error"
            return SourceResult(connection="error", message=detail)
        try:
            payload = json.loads(result.stdout.strip() or "{}")
        except json.JSONDecodeError:
            return SourceResult(connection="error", message="MediaRemote returned invalid JSON.")
        if not isinstance(payload, dict) or not payload.get("title"):
            return SourceResult(connection="waiting", message="No active system Now Playing item.")

        track = normalize_mediaremote_payload(payload)
        self._apply_timeline_reliability(track)
        app_name = track.get("app_name") or "macOS player"
        timeline_note = ""
        if track.get("position_accuracy") == "unavailable":
            timeline_note = " Timeline position is not published by this player."
        return SourceResult(
            connection="ok",
            message=f"Reading {app_name} via macOS MediaRemote.{timeline_note}",
            track=track,
        )

    def _apply_timeline_reliability(self, track: dict[str, Any]) -> None:
        identity = "|".join(
            str(track.get(key) or "")
            for key in ("source_track_id", "title", "artist", "album")
        )
        elapsed = track.get("position")
        now = time.monotonic()
        if identity != self._last_identity:
            self._last_identity = identity
            self._last_elapsed = elapsed
            self._last_elapsed_at = now
            self._timeline_reliable = (
                True if isinstance(elapsed, (int, float)) and elapsed > 0 else None
            )
        elif track.get("is_playing") and isinstance(elapsed, (int, float)):
            if self._last_elapsed is not None and elapsed > self._last_elapsed + 0.25:
                self._timeline_reliable = True
            elif (
                self._last_elapsed is not None
                and abs(elapsed - self._last_elapsed) <= 0.01
                and now - self._last_elapsed_at >= 2.0
            ):
                self._timeline_reliable = False
            if elapsed != self._last_elapsed:
                self._last_elapsed = elapsed
                self._last_elapsed_at = now

        if self._timeline_reliable is False:
            track["position"] = None
            track["position_accuracy"] = "unavailable"
        elif self._timeline_reliable is True:
            track["position_accuracy"] = "reported"
        else:
            track["position_accuracy"] = "unverified"


class MacOSAppleScriptSource:
    name = "macos-applescript"

    def __init__(self, timeout: float = 4.0) -> None:
        self.timeout = timeout

    def poll(self) -> SourceResult:
        if platform.system() != "Darwin":
            return SourceResult(connection="unsupported", message="AppleScript source requires macOS.")
        try:
            result = subprocess.run(
                ["osascript", "-l", "JavaScript", "-e", JXA_SCRIPT],
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return SourceResult(connection="error", message=f"AppleScript source failed: {exc}")

        if result.returncode != 0:
            detail = result.stderr.strip() or "osascript returned an error"
            return SourceResult(connection="permission_or_runtime_error", message=detail)

        try:
            payload = json.loads(result.stdout.strip() or "{}")
        except json.JSONDecodeError:
            return SourceResult(connection="error", message="AppleScript source returned invalid JSON.")

        track = payload.get("track")
        if not isinstance(track, dict) or not track.get("title"):
            return SourceResult(
                connection="waiting",
                message="No active Apple Music or Spotify track.",
            )
        return SourceResult(
            connection="ok",
            message=f"Reading {track.get('app_name', 'macOS player')} via AppleScript.",
            track=_normalize(track),
        )


class MacOSNowPlayingSource:
    """System-wide MediaRemote with AppleScript fallback for Music and Spotify."""

    name = "macos-system"

    def __init__(
        self,
        mediaremote: TrackSource | None = None,
        applescript: TrackSource | None = None,
    ) -> None:
        self.mediaremote = mediaremote or MacOSMediaRemoteSource()
        self.applescript = applescript or MacOSAppleScriptSource()
        self._last_track: dict[str, Any] | None = None

    def poll(self) -> SourceResult:
        system_result = self.mediaremote.poll()
        if system_result.track:
            self._last_track = dict(system_result.track)
            return system_result

        fallback_result = self.applescript.poll()
        if fallback_result.track:
            self._last_track = dict(fallback_result.track)
            return SourceResult(
                connection=fallback_result.connection,
                message=f"{fallback_result.message} MediaRemote: {system_result.connection}.",
                track=fallback_result.track,
            )

        if system_result.connection not in {"waiting", "tool_missing"}:
            return system_result
        if fallback_result.connection not in {"waiting", "tool_missing"}:
            return fallback_result
        inactive_track = None
        if self._last_track:
            inactive_track = {
                **self._last_track,
                "playback_status": "stopped",
                "is_playing": False,
                "position": None,
                "position_accuracy": "unavailable",
            }
            self._last_track = inactive_track
        return SourceResult(
            connection="waiting",
            message="No active system Now Playing item, Apple Music, or Spotify track.",
            track=inactive_track,
        )


def find_nowplaying_cli() -> Path | None:
    configured = os.environ.get("CORD_NOWPLAYING_CLI")
    if configured:
        path = Path(configured).expanduser()
        return path if path.is_file() else None
    if LOCAL_NOWPLAYING_CLI.is_file():
        return LOCAL_NOWPLAYING_CLI
    executable = shutil.which("nowplaying-cli")
    return Path(executable) if executable else None


def normalize_mediaremote_payload(payload: dict[str, Any]) -> dict[str, Any]:
    playing = _boolean(payload.get("playing"))
    rate = _number(payload.get("playbackRate"))
    if playing is None:
        playing = rate is not None and rate > 0
    status = "playing" if playing else "paused"
    bundle_id = str(payload.get("clientBundleIdentifier") or "").strip()
    app_name = BUNDLE_NAMES.get(bundle_id.lower(), bundle_id or "macOS player")
    position = _non_negative_number(payload.get("elapsedTime"))
    return {
        "title": str(payload.get("title") or "").strip(),
        "artist": str(payload.get("artist") or "").strip(),
        "album": str(payload.get("album") or "").strip(),
        "cover_url": _artwork_data_url(payload),
        "app_name": app_name,
        "source_track_id": str(payload.get("uniqueIdentifier") or "").strip(),
        "playback_status": status,
        "is_playing": status == "playing",
        "position": position,
        "duration": _non_negative_number(payload.get("duration")),
        "position_accuracy": "unverified" if position is not None else "unavailable",
    }


def _normalize(track: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": str(track.get("title") or "").strip(),
        "artist": str(track.get("artist") or "").strip(),
        "album": str(track.get("album") or "").strip(),
        "cover_url": str(track.get("cover_url") or "").strip(),
        "app_name": str(track.get("app_name") or "macOS player").strip(),
        "source_track_id": str(track.get("source_track_id") or "").strip(),
        "playback_status": str(track.get("playback_status") or "stopped").lower(),
        "is_playing": bool(track.get("is_playing")),
        "position": _non_negative_number(track.get("position")),
        "duration": _non_negative_number(track.get("duration")),
        "position_accuracy": str(track.get("position_accuracy") or "reported"),
    }


def _artwork_data_url(payload: dict[str, Any]) -> str:
    encoded = payload.get("artworkData")
    if not isinstance(encoded, str) or not encoded:
        return ""
    try:
        raw = base64.b64decode(encoded, validate=True)
    except ValueError:
        return ""
    mime = str(payload.get("artworkMIMEType") or "").strip().lower()
    if not mime.startswith("image/"):
        mime = _image_mime(raw) or ""
    return f"data:{mime};base64,{encoded}" if mime else ""


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


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _boolean(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in {0, 1}:
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "yes", "1"}:
            return True
        if normalized in {"false", "no", "0"}:
            return False
    return None


def _non_negative_number(value: Any) -> float | None:
    number = _number(value)
    return number if number is not None and number >= 0 else None
