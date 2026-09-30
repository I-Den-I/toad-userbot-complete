from __future__ import annotations

import pytest

from toad_userbot.control.parser import ParsedCommand, parse_command


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (".help", ParsedCommand("help", ())),
        ("  .PING  ", ParsedCommand("ping", ())),
        (".logs 50 error", ParsedCommand("logs", ("50", "error"))),
        (".chat set -1001234567890", ParsedCommand("chat", ("set", "-1001234567890"))),
        (".chats жаб чат", ParsedCommand("chats", ("жаб", "чат"))),
        (".export\n48", ParsedCommand("export", ("48",))),
    ],
)
def test_commands(text: str, expected: ParsedCommand) -> None:
    assert parse_command(text, ".") == expected


@pytest.mark.parametrize("text", ["help", "...", ". help", ".", ".123", "", "текст .help"])
def test_not_commands(text: str) -> None:
    assert parse_command(text, ".") is None


def test_custom_prefix() -> None:
    assert parse_command("!ping", "!") == ParsedCommand("ping", ())
    assert parse_command(".ping", "!") is None
