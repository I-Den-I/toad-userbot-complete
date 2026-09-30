"""Time primitives.

The game runs on a fixed UTC+3 offset with no daylight saving time, so a constant offset is
used instead of a named zone. Internally every timestamp is an aware ``datetime`` in UTC.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from typing import Final, Protocol

GAME_TZ: Final = timezone(timedelta(hours=3), name="UTC+3")


class Clock(Protocol):
    """Source of the current time. Injected everywhere so tests can control time."""

    def now(self) -> datetime:
        """Return the current moment as an aware UTC datetime."""
        ...


class SystemClock:
    """Clock backed by the operating system."""

    def now(self) -> datetime:
        return datetime.now(UTC)


def to_game_time(moment: datetime) -> datetime:
    """Convert an aware datetime to the game's UTC+3 offset."""
    if moment.tzinfo is None:
        msg = "naive datetimes are not allowed"
        raise ValueError(msg)
    return moment.astimezone(GAME_TZ)
