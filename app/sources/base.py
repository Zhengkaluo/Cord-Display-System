from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class SourceResult:
    connection: str
    message: str = ""
    track: dict[str, Any] | None = None


class TrackSource(Protocol):
    name: str

    def poll(self) -> SourceResult:
        """Return one normalized track snapshot or a waiting/error status."""
