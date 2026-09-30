from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from toad_userbot.control.format import ago, esc, game_time, human_bytes, human_duration
from toad_userbot.domain.time import GAME_TZ, to_game_time


@pytest.mark.parametrize(
    ("size", "expected"),
    [
        (0, "0 Б"),
        (1023, "1023 Б"),
        (1024, "1.0 КБ"),
        (1536, "1.5 КБ"),
        (5 * 1024**2, "5.0 МБ"),
        (3 * 1024**3, "3.0 ГБ"),
        (2 * 1024**5, "2048.0 ТБ"),
    ],
)
def test_human_bytes(size: int, expected: str) -> None:
    assert human_bytes(size) == expected


@pytest.mark.parametrize(
    ("delta", "expected"),
    [
        (timedelta(seconds=-5), "0 с"),
        (timedelta(seconds=5), "5 с"),
        (timedelta(minutes=4, seconds=5), "4 хв 5 с"),
        (timedelta(hours=2, minutes=0, seconds=59), "2 год 0 хв"),
        (timedelta(days=1, hours=3, minutes=4), "1 д 3 год 4 хв"),
    ],
)
def test_human_duration(delta: timedelta, expected: str) -> None:
    assert human_duration(delta) == expected


def test_game_time_is_utc_plus_three() -> None:
    moment = datetime(2026, 9, 30, 12, 31, 2, tzinfo=UTC)
    assert game_time(moment) == "30.09 15:31:02"
    assert to_game_time(moment).utcoffset() == GAME_TZ.utcoffset(None)


def test_ago() -> None:
    moment = datetime(2026, 9, 30, 12, 31, tzinfo=UTC)
    assert ago(moment, moment + timedelta(minutes=5)) == "30.09 15:31:00 (5 хв 0 с тому)"


def test_naive_datetime_is_rejected() -> None:
    with pytest.raises(ValueError, match="naive"):
        to_game_time(datetime(2026, 9, 30, 12, 31))  # noqa: DTZ001


def test_esc() -> None:
    assert esc("<b>&") == "&lt;b&gt;&amp;"
