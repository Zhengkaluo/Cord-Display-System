from __future__ import annotations

import argparse
import json
import mimetypes
import os
import queue
import re
import sys
import threading
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote, urlparse

from .artist_events import ArtistEventStore, ArtistEventValidationError
from .display_items import DisplayItemStore, DisplayItemValidationError
from .source_runner import SourceRunner
from .sources import build_source
from .sources.factory import SOURCE_MODES
from .state_store import StateStore, StateValidationError


PROJECT_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_ROOT = PROJECT_ROOT / "frontend"
MEDIA_ROOT = PROJECT_ROOT / "media"
CONFIG_PATH = PROJECT_ROOT / "data" / "runtime-config.json"
DATABASE_PATH = PROJECT_ROOT / "data" / "cord-screen.db"
MAX_BODY_BYTES = 1_000_000
MAX_MEDIA_BYTES = 250 * 1024 * 1024
MEDIA_SUFFIXES = {
    ".gif": "image",
    ".jpeg": "image",
    ".jpg": "image",
    ".png": "image",
    ".svg": "image",
    ".webp": "image",
    ".m4v": "video",
    ".mov": "video",
    ".mp4": "video",
    ".webm": "video",
}


class FlowHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(
        self,
        server_address: tuple[str, int],
        handler_class: type[BaseHTTPRequestHandler],
        media_root: Path = MEDIA_ROOT,
        config_path: Path | None = CONFIG_PATH,
        database_path: Path = DATABASE_PATH,
    ):
        super().__init__(server_address, handler_class)
        self.artist_events = ArtistEventStore(database_path)
        self.display_items = DisplayItemStore(database_path)
        self.state_store = StateStore(
            config_path=config_path,
            artist_event_matcher=self.artist_events.find_match,
            display_item_provider=self.display_items.list_eligible,
        )
        if config_path and config_path.is_file():
            self.display_items.migrate_legacy_promotion(
                self.state_store.snapshot()["content"]["promotion"]
            )
        self.media_root = media_root

    def server_close(self) -> None:
        state_store = getattr(self, "state_store", None)
        if state_store is not None:
            state_store.close()
        super().server_close()

    def handle_error(self, request: object, client_address: tuple[str, int]) -> None:
        error = sys.exc_info()[1]
        if isinstance(error, (BrokenPipeError, ConnectionResetError)):
            return
        super().handle_error(request, client_address)


class FlowRequestHandler(BaseHTTPRequestHandler):
    server: FlowHTTPServer

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/":
            self.send_response(HTTPStatus.FOUND)
            self.send_header("Location", "/display")
            self.end_headers()
            return
        if path == "/health":
            self._json_response(
                HTTPStatus.OK,
                {
                    "ok": True,
                    "service": "music-player-flowsystem",
                    "schema_version": self.server.state_store.snapshot()["schema_version"],
                },
            )
            return
        if path == "/api/state":
            self._json_response(HTTPStatus.OK, self.server.state_store.snapshot())
            return
        if path == "/api/events":
            self._serve_events()
            return
        if path == "/api/artist-events":
            self._json_response(
                HTTPStatus.OK,
                {"items": self.server.artist_events.list()},
            )
            return
        if path == "/api/display-items":
            eligible_ids = {
                item["id"] for item in self.server.display_items.list_eligible()
            }
            items = [
                {**item, "eligible": item["id"] in eligible_ids}
                for item in self.server.display_items.list()
            ]
            self._json_response(HTTPStatus.OK, {"items": items})
            return
        if path in {"/display", "/display/"}:
            self._serve_file(FRONTEND_ROOT / "display.html")
            return
        if path in {"/admin", "/admin/"}:
            self._serve_file(FRONTEND_ROOT / "admin.html")
            return
        if path.startswith("/assets/"):
            relative = path.removeprefix("/assets/")
            asset_path = (FRONTEND_ROOT / "assets" / relative).resolve()
            asset_root = (FRONTEND_ROOT / "assets").resolve()
            if asset_path == asset_root or asset_root not in asset_path.parents:
                self._json_response(HTTPStatus.NOT_FOUND, {"error": "not found"})
                return
            self._serve_file(asset_path)
            return
        if path.startswith("/media/"):
            relative = unquote(path.removeprefix("/media/"))
            media_root = self.server.media_root.resolve()
            media_path = (media_root / relative).resolve()
            if media_path == media_root or media_root not in media_path.parents:
                self._json_response(HTTPStatus.NOT_FOUND, {"error": "not found"})
                return
            self._serve_file(media_path, allow_ranges=True)
            return
        self._json_response(HTTPStatus.NOT_FOUND, {"error": "not found"})

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        try:
            payload = self._read_json_body()
            if path == "/api/mock/track":
                state = self.server.state_store.update_track(payload)
                self._json_response(HTTPStatus.OK, state)
                return
            if path == "/api/config":
                state = self.server.state_store.update_config(payload)
                self._json_response(HTTPStatus.OK, state)
                return
            if path == "/api/display":
                state = self.server.state_store.update_display(payload)
                self._json_response(HTTPStatus.OK, state)
                return
            if path == "/api/content/artist_notice":
                state = self.server.state_store.update_content("artist_notice", payload)
                self._json_response(HTTPStatus.OK, state)
                return
            if path == "/api/content/promotion":
                state = self.server.state_store.update_content("promotion", payload)
                self._json_response(HTTPStatus.OK, state)
                return
            if path == "/api/artist-events":
                event = self.server.artist_events.create(payload)
                self.server.state_store.refresh_artist_match()
                self._json_response(HTTPStatus.CREATED, event)
                return
            if path == "/api/display-items":
                item = self.server.display_items.create(payload)
                self._json_response(HTTPStatus.CREATED, item)
                return
            preview_match = re.fullmatch(r"/api/artist-events/(\d+)/preview", path)
            if preview_match:
                event = self.server.artist_events.get(int(preview_match.group(1)))
                if not event:
                    self._json_response(HTTPStatus.NOT_FOUND, {"error": "artist event not found"})
                    return
                state = self.server.state_store.preview_artist_event(event)
                self._json_response(HTTPStatus.OK, state)
                return
            preview_match = re.fullmatch(r"/api/display-items/(\d+)/preview", path)
            if preview_match:
                item = self.server.display_items.get(int(preview_match.group(1)))
                if not item:
                    self._json_response(HTTPStatus.NOT_FOUND, {"error": "display item not found"})
                    return
                state = self.server.state_store.preview_display_item(item)
                self._json_response(HTTPStatus.OK, state)
                return
            self._json_response(HTTPStatus.NOT_FOUND, {"error": "not found"})
        except (StateValidationError, ArtistEventValidationError, DisplayItemValidationError) as exc:
            self._json_response(HTTPStatus.UNPROCESSABLE_ENTITY, {"error": str(exc)})
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._json_response(HTTPStatus.BAD_REQUEST, {"error": "invalid JSON body"})
        except ValueError as exc:
            self._json_response(HTTPStatus.BAD_REQUEST, {"error": str(exc)})

    def do_PUT(self) -> None:
        path = urlparse(self.path).path
        try:
            if path == "/api/media":
                payload = self._save_media_upload()
                self._json_response(HTTPStatus.CREATED, payload)
                return
            event_match = re.fullmatch(r"/api/artist-events/(\d+)", path)
            if event_match:
                payload = self._read_json_body()
                event = self.server.artist_events.update(int(event_match.group(1)), payload)
                if not event:
                    self._json_response(HTTPStatus.NOT_FOUND, {"error": "artist event not found"})
                    return
                self.server.state_store.refresh_artist_match()
                self._json_response(HTTPStatus.OK, event)
                return
            item_match = re.fullmatch(r"/api/display-items/(\d+)", path)
            if item_match:
                payload = self._read_json_body()
                item = self.server.display_items.update(int(item_match.group(1)), payload)
                if not item:
                    self._json_response(HTTPStatus.NOT_FOUND, {"error": "display item not found"})
                    return
                self._json_response(HTTPStatus.OK, item)
                return
            self._json_response(HTTPStatus.NOT_FOUND, {"error": "not found"})
        except (StateValidationError, ArtistEventValidationError, DisplayItemValidationError) as exc:
            self._json_response(HTTPStatus.UNPROCESSABLE_ENTITY, {"error": str(exc)})
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._json_response(HTTPStatus.BAD_REQUEST, {"error": "invalid JSON body"})
        except ValueError as exc:
            self._json_response(HTTPStatus.BAD_REQUEST, {"error": str(exc)})

    def do_DELETE(self) -> None:
        path = urlparse(self.path).path
        event_match = re.fullmatch(r"/api/artist-events/(\d+)", path)
        if event_match:
            deleted = self.server.artist_events.delete(int(event_match.group(1)))
            if not deleted:
                self._json_response(HTTPStatus.NOT_FOUND, {"error": "artist event not found"})
                return
            self.server.state_store.refresh_artist_match()
            self._json_response(HTTPStatus.OK, {"ok": True})
            return

        item_match = re.fullmatch(r"/api/display-items/(\d+)", path)
        if item_match:
            deleted = self.server.display_items.delete(int(item_match.group(1)))
            if not deleted:
                self._json_response(HTTPStatus.NOT_FOUND, {"error": "display item not found"})
                return
            self._json_response(HTTPStatus.OK, {"ok": True})
            return

        self._json_response(HTTPStatus.NOT_FOUND, {"error": "not found"})

    def _read_json_body(self) -> dict[str, Any]:
        raw_length = self.headers.get("Content-Length", "0")
        try:
            length = int(raw_length)
        except ValueError as exc:
            raise ValueError("invalid Content-Length") from exc
        if length <= 0:
            raise ValueError("JSON body is required")
        if length > MAX_BODY_BYTES:
            raise ValueError("request body is too large")
        raw = self.rfile.read(length)
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("JSON body must be an object")
        return payload

    def _serve_events(self) -> None:
        subscriber = self.server.state_store.subscribe()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        try:
            self._write_event(self.server.state_store.snapshot())
            while True:
                try:
                    state = subscriber.get(timeout=15)
                    self._write_event(state)
                except queue.Empty:
                    self.wfile.write(b": ping\n\n")
                    self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            self.server.state_store.unsubscribe(subscriber)

    def _write_event(self, state: dict[str, Any]) -> None:
        payload = json.dumps(state, ensure_ascii=False, separators=(",", ":"))
        self.wfile.write(f"event: state\ndata: {payload}\n\n".encode("utf-8"))
        self.wfile.flush()

    def _save_media_upload(self) -> dict[str, Any]:
        raw_length = self.headers.get("Content-Length", "0")
        try:
            length = int(raw_length)
        except ValueError as exc:
            raise ValueError("invalid Content-Length") from exc
        if length <= 0:
            raise ValueError("media file is required")
        if length > MAX_MEDIA_BYTES:
            raise ValueError("media file is larger than 250 MB")

        original_name = unquote(self.headers.get("X-Filename", "")).strip()
        safe_name, media_type = _safe_media_name(original_name)
        media_root = self.server.media_root
        media_root.mkdir(parents=True, exist_ok=True)
        target = _available_media_target(media_root, safe_name)
        safe_name = target.name
        temporary = media_root / f".{safe_name}.{threading.get_ident()}.part"
        remaining = length
        try:
            with temporary.open("wb") as output:
                while remaining:
                    chunk = self.rfile.read(min(1024 * 1024, remaining))
                    if not chunk:
                        raise ValueError("media upload ended unexpectedly")
                    output.write(chunk)
                    remaining -= len(chunk)
            os.replace(temporary, target)
        finally:
            if temporary.exists():
                temporary.unlink()
        return {
            "ok": True,
            "media_type": media_type,
            "filename": safe_name,
            "url": f"/media/{quote(safe_name)}",
        }

    def _serve_file(self, path: Path, *, allow_ranges: bool = False) -> None:
        if not path.is_file():
            self._json_response(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return
        content_type, _ = mimetypes.guess_type(path.name)
        media_type = content_type or "application/octet-stream"
        if media_type.startswith("text/") or media_type in {"application/javascript", "application/json"}:
            media_type = f"{media_type}; charset=utf-8"

        file_size = path.stat().st_size
        start, end = 0, max(0, file_size - 1)
        status = HTTPStatus.OK
        range_header = self.headers.get("Range") if allow_ranges else None
        if range_header:
            parsed_range = _parse_byte_range(range_header, file_size)
            if parsed_range is None:
                self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                self.send_header("Content-Range", f"bytes */{file_size}")
                self.end_headers()
                return
            start, end = parsed_range
            status = HTTPStatus.PARTIAL_CONTENT

        content_length = 0 if file_size == 0 else end - start + 1
        self.send_response(status)
        self.send_header("Content-Type", media_type)
        self.send_header("Content-Length", str(content_length))
        self.send_header("Cache-Control", "no-store")
        if allow_ranges:
            self.send_header("Accept-Ranges", "bytes")
        if status == HTTPStatus.PARTIAL_CONTENT:
            self.send_header("Content-Range", f"bytes {start}-{end}/{file_size}")
        self.end_headers()
        if content_length:
            with path.open("rb") as source:
                source.seek(start)
                remaining = content_length
                while remaining:
                    chunk = source.read(min(1024 * 1024, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)

    def _json_response(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format: str, *args: object) -> None:
        message = format % args
        print(f"[{self.log_date_time_string()}] {self.client_address[0]} {message}")


def _safe_media_name(original_name: str) -> tuple[str, str]:
    name = Path(original_name).name
    suffix = Path(name).suffix.lower()
    media_type = MEDIA_SUFFIXES.get(suffix)
    if not name or not media_type:
        raise StateValidationError(
            "supported media: PNG, JPG, WebP, GIF, SVG, MP4, WebM, MOV, M4V"
        )
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", Path(name).stem).strip("-._")
    if not stem:
        stem = "visual"
    return f"{stem[:80]}{suffix}", media_type


def _available_media_target(media_root: Path, safe_name: str) -> Path:
    target = media_root / safe_name
    if not target.exists():
        return target
    suffix = target.suffix
    stem = target.stem
    for index in range(2, 10_000):
        candidate = media_root / f"{stem}-{index}{suffix}"
        if not candidate.exists():
            return candidate
    raise ValueError("too many media files with the same name")


def _parse_byte_range(value: str, file_size: int) -> tuple[int, int] | None:
    match = re.fullmatch(r"bytes=(\d*)-(\d*)", value.strip())
    if not match or file_size <= 0:
        return None
    start_text, end_text = match.groups()
    if not start_text:
        length = int(end_text or 0)
        if length <= 0:
            return None
        return max(0, file_size - length), file_size - 1
    start = int(start_text)
    end = int(end_text) if end_text else file_size - 1
    if start >= file_size or start > end:
        return None
    return start, min(end, file_size - 1)


def create_server(
    host: str = "127.0.0.1",
    port: int = 8765,
    *,
    media_root: Path = MEDIA_ROOT,
    config_path: Path | None = CONFIG_PATH,
    database_path: Path = DATABASE_PATH,
) -> FlowHTTPServer:
    return FlowHTTPServer(
        (host, port),
        FlowRequestHandler,
        media_root,
        config_path,
        database_path,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="CORD store-screen local service")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8765, type=int)
    parser.add_argument("--source", choices=sorted(SOURCE_MODES), default="mock")
    parser.add_argument("--poll-interval", default=2.0, type=float)
    parser.add_argument("--open", action="store_true", help="open display and admin pages")
    args = parser.parse_args()

    server = create_server(args.host, args.port)
    source = build_source(args.source)
    server.state_store.update_config({"source_mode": args.source})
    if source.name != "mock":
        server.state_store.prepare_live_source()
    source_runner = SourceRunner(source, server.state_store, interval=args.poll_interval)
    source_runner.start()
    display_url = f"http://{args.host}:{server.server_port}/display"
    admin_url = f"http://{args.host}:{server.server_port}/admin"
    print("CORD Music Player FlowSystem")
    print(f"Platform source: {source.name}")
    print(f"Display: {display_url}")
    print(f"Admin:   {admin_url}")
    print("Press Ctrl+C to stop.")

    if args.open:
        threading.Timer(0.4, lambda: webbrowser.open(display_url)).start()
        threading.Timer(0.8, lambda: webbrowser.open(admin_url)).start()

    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        source_runner.stop()
        server.server_close()


if __name__ == "__main__":
    main()
