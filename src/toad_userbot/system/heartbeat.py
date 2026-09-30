"""Liveness file for the container healthcheck."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

import structlog

from toad_userbot.domain.time import Clock

log = structlog.get_logger(__name__)


class Heartbeat:
    """Periodically rewrites a file; its modification time proves the event loop is alive."""

    def __init__(self, path: Path, clock: Clock, interval: float = 30.0) -> None:
        self._path = path
        self._clock = clock
        self._interval = interval

    def beat(self) -> None:
        self._path.write_text(self._clock.now().isoformat(), encoding="utf-8")

    async def run(self) -> None:
        while True:
            try:
                self.beat()
            except OSError as exc:
                log.warning("heartbeat.write_failed", error=str(exc))
            await asyncio.sleep(self._interval)


def is_alive(path: Path, max_age: float, now: float | None = None) -> bool:
    """True if the heartbeat file was updated within ``max_age`` seconds."""
    try:
        modified = path.stat().st_mtime
    except OSError:
        return False
    current = time.time() if now is None else now
    return current - modified <= max_age
