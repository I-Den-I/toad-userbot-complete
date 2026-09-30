from __future__ import annotations

import pytest

from tests.fakes import T0
from toad_userbot.control.dispatcher import ControlDispatcher
from toad_userbot.control.parser import ParsedCommand
from toad_userbot.control.registry import (
    Command,
    CommandContext,
    CommandRegistry,
    CommandResult,
    UsageError,
)


async def _echo(context: CommandContext) -> CommandResult:
    return CommandResult(html=f"args={','.join(context.args)}")


async def _usage(_: CommandContext) -> CommandResult:
    msg = "погане <число>"
    raise UsageError(msg)


async def _boom(_: CommandContext) -> CommandResult:
    msg = "unexpected"
    raise RuntimeError(msg)


@pytest.fixture
def dispatcher() -> ControlDispatcher:
    registry = CommandRegistry()
    registry.register_all(
        [
            Command("echo", "Тест", "повторити", _echo, usage="[args]", aliases=("e",)),
            Command("usage", "Тест", "помилка аргументів", _usage, usage="<n>"),
            Command("boom", "Тест", "падає", _boom),
        ]
    )
    return ControlDispatcher(registry, ".")


async def _run(dispatcher: ControlDispatcher, text: str) -> CommandResult:
    parsed = dispatcher.parse(text)
    assert parsed is not None
    return await dispatcher.dispatch(parsed, sent_at=T0, received_at=T0)


async def test_result_echoes_the_command(dispatcher: ControlDispatcher) -> None:
    result = await _run(dispatcher, ".echo a b")
    assert result.edit_original
    assert result.html == "<code>.echo a b</code>\n\nargs=a,b"


async def test_alias_resolves_to_command(dispatcher: ControlDispatcher) -> None:
    result = await _run(dispatcher, ".e x")
    assert result.html.startswith("<code>.echo x</code>")


async def test_unknown_command_is_a_separate_reply(dispatcher: ControlDispatcher) -> None:
    result = await _run(dispatcher, ".nope")
    assert not result.edit_original
    assert "Невідома команда" in result.html
    assert "<code>.help</code>" in result.html


async def test_usage_error_is_escaped_and_shows_usage(dispatcher: ControlDispatcher) -> None:
    result = await _run(dispatcher, ".usage")
    assert "погане &lt;число&gt;" in result.html
    assert "<code>.usage &lt;n&gt;</code>" in result.html


async def test_unexpected_error_is_reported_not_raised(
    dispatcher: ControlDispatcher, caplog: pytest.LogCaptureFixture
) -> None:
    result = await _run(dispatcher, ".boom")
    assert "Помилка" in result.html
    assert ".logs 20 error" in result.html


async def test_dispatch_accepts_parsed_command_directly(dispatcher: ControlDispatcher) -> None:
    result = await dispatcher.dispatch(ParsedCommand("echo", ()), sent_at=T0, received_at=T0)
    assert result.html.endswith("args=")


def test_duplicate_names_are_rejected() -> None:
    registry = CommandRegistry()
    registry.register(Command("ping", "g", "s", _echo, aliases=("p",)))
    with pytest.raises(ValueError, match="already registered"):
        registry.register(Command("pong", "g", "s", _echo, aliases=("p",)))
    assert registry.resolve("pong") is None
