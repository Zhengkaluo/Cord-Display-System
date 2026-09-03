from __future__ import annotations

from .base import SourceResult


class MockSource:
    name = "mock"

    def poll(self) -> SourceResult:
        return SourceResult(connection="ok", message="Mock data source is active.")
