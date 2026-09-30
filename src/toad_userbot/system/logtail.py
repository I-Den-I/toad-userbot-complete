"""Reading the tail of the log file without loading all of it."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Final

LEVELS: Final[tuple[str, ...]] = ("debug", "info", "warning", "error", "critical")

# structlog's ConsoleRenderer writes the level as "[info     ]".
_LEVEL_PATTERN = re.compile(r"\[(?P<level>debug|info|warning|error|critical)\s*\]")

_BLOCK_SIZE = 8192


def tail_lines(path: Path, count: int) -> list[str]:
    """Return up to ``count`` last lines of the file. A missing file yields no lines."""
    if count <= 0 or not path.exists():
        return []

    with path.open("rb") as handle:
        handle.seek(0, 2)
        position = handle.tell()
        buffer = b""
        # One extra line guarantees the first returned line is complete.
        while position > 0 and buffer.count(b"\n") <= count:
            step = min(_BLOCK_SIZE, position)
            position -= step
            handle.seek(position)
            buffer = handle.read(step) + buffer

    lines = buffer.decode("utf-8", errors="replace").splitlines()
    return lines[-count:]


def filter_by_level(lines: list[str], min_level: str) -> list[str]:
    """Keep lines whose level is at least ``min_level``. Continuation lines are dropped."""
    threshold = LEVELS.index(min_level)
    kept: list[str] = []
    for line in lines:
        match = _LEVEL_PATTERN.search(line)
        if match is not None and LEVELS.index(match["level"]) >= threshold:
            kept.append(line)
    return kept
