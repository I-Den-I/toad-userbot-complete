"""Startup helpers of the composition root and the Telethon info adapter, with fakes."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

import pytest

from tests.fakes import BOT_ID, CHAT_ID, FakeMeta, FakeTelegram
from toad_userbot.app import EXIT_DISCONNECTED, _resolve_bot, _resolve_target, _wait_for_stop
from toad_userbot.runtime import TARGET_CHAT_META_KEY, ChatSource, Shutdown
from toad_userbot.telegram.info import TelethonInfo


@dataclass
class FakeConnection:
    resolved: list[str] = field(default_factory=list)
    lost: asyncio.Event = field(default_factory=asyncio.Event)

    async def resolve_user_id(self, username: str) -> int:
        self.resolved.append(username)
        return BOT_ID

    async def wait_disconnected(self) -> None:
        await self.lost.wait()


async def test_bot_id_is_resolved_once_and_cached() -> None:
    connection, meta = FakeConnection(), FakeMeta()

    first = await _resolve_bot(connection, meta, "toadbot")
    second = await _resolve_bot(connection, meta, "toadbot")

    assert first == second
    assert first.id == BOT_ID
    assert connection.resolved == ["toadbot"]


@pytest.mark.parametrize(
    ("stored", "config_id", "expected"),
    [
        (None, CHAT_ID, (CHAT_ID, "Болото", ChatSource.CONFIG)),
        ("-100555", CHAT_ID, (-100555, "Робочий чат", ChatSource.OVERRIDE)),
        (None, -100999, (-100999, None, ChatSource.CONFIG)),  # left the group: keep the id
        (None, None, (None, None, ChatSource.NONE)),
    ],
)
async def test_target_chat_resolution(
    stored: str | None, config_id: int | None, expected: tuple[object, ...]
) -> None:
    meta = FakeMeta({TARGET_CHAT_META_KEY: stored} if stored else {})

    target = await _resolve_target(FakeTelegram(), meta, config_id)

    assert (target.id, target.title, target.source) == expected


async def test_shutdown_request_stops_waiting() -> None:
    shutdown = Shutdown()
    connection = FakeConnection()
    asyncio.get_running_loop().call_soon(shutdown.request, 0)

    await asyncio.wait_for(_wait_for_stop(connection, shutdown), timeout=1)

    assert shutdown.exit_code == 0


async def test_permanent_disconnect_exits_with_error() -> None:
    shutdown = Shutdown()
    connection = FakeConnection()
    connection.lost.set()

    await asyncio.wait_for(_wait_for_stop(connection, shutdown), timeout=1)

    assert shutdown.exit_code == EXIT_DISCONNECTED


# --- TelethonInfo --------------------------------------------------------------------------------


class FakeTelethonClient:
    def __init__(self) -> None:
        self.requests: list[Any] = []
        self.dialogs = [
            SimpleNamespace(id=CHAT_ID, name="Болото", is_group=True),
            SimpleNamespace(id=777, name="Особисті", is_group=False),
            SimpleNamespace(id=-100555, name="Робочий чат", is_group=True),
            SimpleNamespace(id=-100666, name="Ще болото", is_group=True),
        ]

    def is_connected(self) -> bool:
        return True

    async def __call__(self, request: Any) -> None:
        self.requests.append(request)

    async def get_me(self) -> Any:
        return SimpleNamespace(id=42, first_name="Скала", last_name=None, username="skala")

    async def iter_dialogs(self) -> AsyncIterator[Any]:
        for dialog in self.dialogs:
            yield dialog


async def test_telethon_info_adapter() -> None:
    client = FakeTelethonClient()
    info = TelethonInfo(client)

    assert info.is_connected()
    assert await info.ping() >= 0
    assert type(client.requests[0]).__name__ == "PingRequest"
    account = await info.account()
    assert (account.id, account.username) == (42, "skala")
    assert [group.title for group in await info.groups("болот", limit=10)] == [
        "Болото",
        "Ще болото",
    ]
    assert len(await info.groups(None, limit=2)) == 2
    found = await info.find_group(-100555)
    assert found is not None
    assert found.title == "Робочий чат"
    assert await info.find_group(777) is None  # private chats are not groups
