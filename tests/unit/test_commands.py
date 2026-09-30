from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

import pytest

from tests.fakes import (
    BOT_ID,
    CHAT_ID,
    T0,
    FakeClock,
    FakeMessageStats,
    FakeMeta,
    FakeTelegram,
)
from toad_userbot.config import Paths
from toad_userbot.control.commands import CommandDeps, build_commands
from toad_userbot.control.dispatcher import ControlDispatcher
from toad_userbot.control.registry import CommandRegistry, CommandResult
from toad_userbot.recorder.models import RecordedMessage
from toad_userbot.recorder.policy import RecordingPolicy
from toad_userbot.recorder.service import Recorder
from toad_userbot.runtime import (
    EXIT_RESTART,
    TARGET_CHAT_META_KEY,
    BotIdentity,
    BuildInfo,
    ChatSource,
    Runtime,
    Shutdown,
    TargetChat,
)


class NullStore:
    async def add(self, message: RecordedMessage) -> None:
        return None

    async def mark_deleted(self, chat_id: int, msg_ids: Sequence[int], at: datetime) -> int:
        return 0


class Harness:
    def __init__(self, tmp_path: Path, clock: FakeClock) -> None:
        self.paths = Paths(tmp_path / "data")
        self.paths.ensure()
        self.telegram = FakeTelegram()
        self.meta = FakeMeta()
        self.messages = FakeMessageStats()
        self.target = TargetChat(CHAT_ID, "Болото", ChatSource.CONFIG)
        self.runtime = Runtime(
            started_at=T0,
            build=BuildInfo("0.1.0", "abcdef1234567"),
            paths=self.paths,
            clock=clock,
            shutdown=Shutdown(),
            target=self.target,
            bot=BotIdentity("toadbot", BOT_ID),
            config_chat_id=CHAT_ID,
        )
        self.recorder = Recorder(
            store=NullStore(),
            policy=RecordingPolicy(bot_id=BOT_ID, bot_username="toadbot"),
            clock=clock,
        )
        registry = CommandRegistry()
        registry.register_all(
            build_commands(
                CommandDeps(
                    runtime=self.runtime,
                    telegram=self.telegram,
                    recorder=self.recorder,
                    messages=self.messages,
                    meta=self.meta,
                    registry=registry,
                    prefix=".",
                )
            )
        )
        self.dispatcher = ControlDispatcher(registry, ".")

    async def run(self, text: str) -> CommandResult:
        parsed = self.dispatcher.parse(text)
        assert parsed is not None
        return await self.dispatcher.dispatch(parsed, sent_at=T0, received_at=T0)


@pytest.fixture
def harness(tmp_path: Path, clock: FakeClock) -> Harness:
    clock.advance(hours=2, minutes=5)
    return Harness(tmp_path, clock)


EXPECTED_COMMANDS = [
    "help", "ping", "uptime", "version", "restart",
    "cpu", "mem", "disk", "sys", "logs",
    "status", "export", "chat", "chats",
]  # fmt: skip


async def test_help_lists_every_command_by_group(harness: Harness) -> None:
    result = await harness.run(".help")
    for name in EXPECTED_COMMANDS:
        assert f"<code>.{name}" in result.html
    assert result.html.index("Загальні") < result.html.index("Сервер")


@pytest.mark.parametrize("name", EXPECTED_COMMANDS)
async def test_every_command_runs_without_arguments(harness: Harness, name: str) -> None:
    result = await harness.run(f".{name}")
    assert "Помилка" not in result.html


async def test_ping(harness: Harness) -> None:
    result = await harness.run(".ping")
    assert "87 мс" in result.html
    assert "< 1 с" in result.html


async def test_uptime_and_version(harness: Harness) -> None:
    assert "2 год 5 хв" in (await harness.run(".uptime")).html
    version = (await harness.run(".v")).html
    assert "0.1.0" in version
    assert "abcdef1234567" in version


async def test_restart_requests_shutdown_only_after_reply(harness: Harness) -> None:
    shutdown = harness.runtime.shutdown
    result = await harness.run(".restart")
    requested_before_reply = shutdown.requested
    assert result.after_reply is not None

    result.after_reply()

    assert (requested_before_reply, shutdown.requested) == (False, True)
    assert shutdown.exit_code == EXIT_RESTART


async def test_logs_inline_and_level_filter(harness: Harness) -> None:
    harness.paths.log_file.write_text(
        "t [info     ] started\nt [error    ] exploded <b>\nt [info     ] recovered\n",
        encoding="utf-8",
    )

    everything = await harness.run(".logs 2")
    errors = await harness.run(".logs error")

    assert "Останні 2 рядків" in everything.html
    assert "recovered" in everything.html
    assert "started" not in everything.html
    assert "exploded &lt;b&gt;" in errors.html
    assert "recovered" not in errors.html


async def test_long_logs_go_to_a_file(harness: Harness) -> None:
    harness.paths.log_file.write_text(
        "".join(f"t [info     ] event number {index}\n" for index in range(400)), encoding="utf-8"
    )

    result = await harness.run(".logs 300")

    assert result.attachment is not None
    assert result.attachment.filename == "userbot-log.txt"
    assert b"event number 399" in result.attachment.content


@pytest.mark.parametrize("args", ["abc", "0", "501", "10 verbose"])
async def test_logs_rejects_bad_arguments(harness: Harness, args: str) -> None:
    result = await harness.run(f".logs {args}")
    assert "Використання" in result.html


async def test_status(harness: Harness) -> None:
    html = (await harness.run(".status")).html
    assert "Болото" in html
    assert str(CHAT_ID) in html
    assert "@toadbot" in html
    assert "у БД: 10 (від бота 6), за 24 год: 4" in html
    assert "abcdef1" in html


async def test_status_warns_when_chat_is_not_configured(harness: Harness) -> None:
    harness.target.update(None, None, ChatSource.NONE)
    assert "не налаштовано" in (await harness.run(".status")).html


async def test_export_builds_jsonl_attachment(harness: Harness) -> None:
    harness.messages.rows = [{"msg_id": 1, "text": "Жаба инфо"}, {"msg_id": 2, "text": "ок"}]

    result = await harness.run(".export 48")

    assert result.attachment is not None
    assert result.attachment.filename.endswith("-48h.jsonl")
    lines = result.attachment.content.decode().splitlines()
    assert [json.loads(line)["msg_id"] for line in lines] == [1, 2]
    assert not result.attachment.caption.startswith(".")


async def test_export_without_rows(harness: Harness) -> None:
    result = await harness.run(".export")
    assert result.attachment is None
    assert "Немає записів за останні 24 год" in result.html


@pytest.mark.parametrize("args", ["0", "721", "x", "1 2"])
async def test_export_rejects_bad_hours(harness: Harness, args: str) -> None:
    assert "Використання" in (await harness.run(f".export {args}")).html


async def test_chat_set_and_reset(harness: Harness) -> None:
    result = await harness.run(".chat set -100555")

    target = harness.target
    assert "Робочий чат" in result.html
    assert (target.id, target.source) == (-100555, ChatSource.OVERRIDE)
    assert harness.meta.values[TARGET_CHAT_META_KEY] == "-100555"

    await harness.run(".chat reset")

    assert (target.id, target.title, target.source) == (CHAT_ID, "Болото", ChatSource.CONFIG)
    assert TARGET_CHAT_META_KEY not in harness.meta.values


@pytest.mark.parametrize("args", ["set -100999", "set abc", "delete", "set"])
async def test_chat_rejects_bad_input(harness: Harness, args: str) -> None:
    result = await harness.run(f".chat {args}")
    assert "Використання" in result.html
    assert harness.target.id == CHAT_ID


async def test_chats_filters_groups(harness: Harness) -> None:
    result = await harness.run(".chats болот")
    assert "Болото" in result.html
    assert "Робочий чат" not in result.html
    assert "Нічого не знайдено" in (await harness.run(".chats нема")).html
