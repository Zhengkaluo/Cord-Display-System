from __future__ import annotations

import json
import threading

from .sources.base import TrackSource
from .state_store import StateStore


class SourceRunner:
    def __init__(self, source: TrackSource, store: StateStore, interval: float = 2.0) -> None:
        self.source = source
        self.store = store
        self.interval = max(0.5, interval)
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_track_key = ""
        self._last_system_key = ""

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, name="track-source", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=max(2.0, self.interval + 0.5))

    def _run(self) -> None:
        while not self._stop_event.is_set():
            result = self.source.poll()
            system_key = json.dumps(
                [self.source.name, result.connection, result.message],
                ensure_ascii=False,
            )
            if system_key != self._last_system_key:
                self.store.update_system(
                    source=self.source.name,
                    connection=result.connection,
                    message=result.message,
                )
                self._last_system_key = system_key

            if result.track:
                track_key = json.dumps(result.track, ensure_ascii=False, sort_keys=True)
                if track_key != self._last_track_key:
                    self.store.update_track(result.track)
                    self._last_track_key = track_key
            self._stop_event.wait(self.interval)
