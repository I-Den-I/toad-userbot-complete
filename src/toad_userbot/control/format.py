"""Formatting helpers for command replies (Telegram HTML)."""

from __future__ import annotations

import html
from datetime import datetime, timedelta

from toad_userbot.domain.time import to_game_time

_BYTE_UNITS = ("Б", "КБ", "МБ", "ГБ", "ТБ")
_KIB = 1024


def esc(value: object) -> str:
    return html.escape(str(value), quote=False)


def code(value: object) -> str:
    return f"<code>{esc(value)}</code>"


def pre(text: str) -> str:
    return f"<pre>{esc(text)}</pre>"


def human_bytes(size: float) -> str:
    value = float(size)
    index = 0
    while abs(value) >= _KIB and index < len(_BYTE_UNITS) - 1:
        value /= _KIB
        index += 1
    return (
        f"{value:.0f} {_BYTE_UNITS[index]}" if index == 0 else f"{value:.1f} {_BYTE_UNITS[index]}"
    )


def human_duration(delta: timedelta) -> str:
    """``2 д 3 год 4 хв`` for long spans, ``4 хв 5 с`` or ``5 с`` for short ones."""
    total = max(0, int(delta.total_seconds()))
    days, rest = divmod(total, 86_400)
    hours, rest = divmod(rest, 3_600)
    minutes, seconds = divmod(rest, 60)

    if days:
        return f"{days} д {hours} год {minutes} хв"
    if hours:
        return f"{hours} год {minutes} хв"
    if minutes:
        return f"{minutes} хв {seconds} с"
    return f"{seconds} с"


def game_time(moment: datetime) -> str:
    return to_game_time(moment).strftime("%d.%m %H:%M:%S")


def ago(moment: datetime, now: datetime) -> str:
    return f"{game_time(moment)} ({human_duration(now - moment)} тому)"


def percent(value: float) -> str:
    return f"{value:.1f}%"
