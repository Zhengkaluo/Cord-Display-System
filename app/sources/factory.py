from __future__ import annotations

import platform

from .base import TrackSource
from .macos import MacOSNowPlayingSource
from .mock import MockSource
from .windows import WindowsSMTCSource


SOURCE_MODES = {"auto", "mock", "macos", "windows"}


def build_source(mode: str = "auto", system: str | None = None) -> TrackSource:
    if mode not in SOURCE_MODES:
        raise ValueError(f"unknown source mode: {mode}")
    detected = system or platform.system()
    if mode == "mock":
        return MockSource()
    if mode == "macos" or (mode == "auto" and detected == "Darwin"):
        return MacOSNowPlayingSource()
    if mode == "windows" or (mode == "auto" and detected == "Windows"):
        return WindowsSMTCSource()
    return MockSource()
