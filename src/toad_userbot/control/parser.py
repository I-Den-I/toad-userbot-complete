"""Parsing of ``.command arg1 arg2`` messages."""

from __future__ import annotations

import re
from dataclasses import dataclass

_COMMAND = re.compile(r"^(?P<name>[^\W\d_][\w-]*)(?:\s+(?P<args>.*))?$", re.DOTALL)


@dataclass(frozen=True, slots=True)
class ParsedCommand:
    name: str
    args: tuple[str, ...]


def parse_command(text: str, prefix: str) -> ParsedCommand | None:
    """Return the parsed command, or ``None`` if the text is not a command.

    The name must follow the prefix immediately and start with a letter, so ordinary notes
    such as ``...`` or ``. hello`` are not treated as commands.
    """
    stripped = text.strip()
    if not stripped.startswith(prefix):
        return None
    match = _COMMAND.match(stripped[len(prefix) :])
    if match is None:
        return None
    args = tuple(match["args"].split()) if match["args"] else ()
    return ParsedCommand(name=match["name"].casefold(), args=args)
