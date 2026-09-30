"""Router and control bridge with Telethon's own message class and a fake client."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest
from telethon.tl import types
from telethon.tl.custom.message import Message

from tests.fakes import BOT_ID, CHAT_ID, OTHER_ID, SELF_ID, T0, FakeClock
from toad_userbot.control.dispatcher import ControlDispatcher
from toad_userbot.control.registry import (
    Attachment,
    Command,
    CommandContext,
    CommandRegistry,
    CommandResult,
)
from toad_userbot.recorder.models import MessageEvent, RecordedMessage
from toad_userbot.recorder.policy import RecordingPolicy
from toad_userbot.recorder.service import Recorder
from toad_userbot.runtime import ChatSource, TargetChat
from toad_userbot.telegram.control_bridge import ControlBridge
from toad_userbot.telegram.router import TelegramRouter

CHANNEL_ID = 1234567890


@dataclass
class MemoryStore:
    added: list[RecordedMessage] = field(default_factory=list)
    deleted: list[tuple[int, list[int]]] = field(default_factory=list)

    async def add(self, message: RecordedMessage) -> None:
        self.added.append(message)

    async def mark_deleted(self, chat_id: int, msg_ids: Sequence[int], at: datetime) -> int:
        self.deleted.append((chat_id, list(msg_ids)))
        return len(msg_ids)


@dataclass
class FakeClient:
    handlers: list[tuple[Any, Any]] = field(default_factory=list)
    sent_files: list[dict[str, Any]] = field(default_factory=list)

    def add_event_handler(self, callback: Any, event: Any) -> None:
        self.handlers.append((callback, event))

    async def send_file(self, entity: str, file: Any, **kwargs: Any) -> None:
        self.sent_files.append({"entity": entity, "name": file.name, **kwargs})


class OwnMessage:
    """Minimal stand-in for a Saved Messages message typed by the owner."""

    def __init__(self, text: str, *, date: datetime = T0, out: bool = True) -> None:
        self.id = 500
        self.message = text
        self.date = date
        self.out = out
        self.media: object | None = None
        self.fwd_from: object | None = None
        self.edits: list[str] = []
        self.replies: list[str] = []

    async def edit(self, text: str, **_: Any) -> None:
        self.edits.append(text)

    async def reply(self, text: str, **_: Any) -> None:
        self.replies.append(text)


def _chat_message(msg_id: int, sender: int, text: str, *, peer: int = CHANNEL_ID) -> Message:
    return Message(
        id=msg_id,
        peer_id=types.PeerChannel(peer),
        from_id=types.PeerUser(sender),
        date=T0,
        message=text,
    )


def _dispatcher() -> ControlDispatcher:
    async def hello(_: CommandContext) -> CommandResult:
        return CommandResult(html="hi")

    async def big(_: CommandContext) -> CommandResult:
        return CommandResult(html="x" * 5000)

    async def report(_: CommandContext) -> CommandResult:
        return CommandResult(html="ok", attachment=Attachment("r.txt", b"data", "📄 r"))

    registry = CommandRegistry()
    registry.register_all(
        [
            Command("hello", "t", "s", hello),
            Command("big", "t", "s", big),
            Command("report", "t", "s", report),
        ]
    )
    return ControlDispatcher(registry, ".")


@pytest.fixture
def client() -> FakeClient:
    return FakeClient()


@pytest.fixture
def bridge(client: FakeClient, clock: FakeClock) -> ControlBridge:
    return ControlBridge(client=client, dispatcher=_dispatcher(), clock=clock, started_at=T0)


@pytest.fixture
def store() -> MemoryStore:
    return MemoryStore()


@pytest.fixture
def target() -> TargetChat:
    return TargetChat(CHAT_ID, "Болото", ChatSource.CONFIG)


@pytest.fixture
def router(
    client: FakeClient,
    bridge: ControlBridge,
    store: MemoryStore,
    target: TargetChat,
    clock: FakeClock,
) -> TelegramRouter:
    recorder = Recorder(
        store=store, policy=RecordingPolicy(bot_id=BOT_ID, bot_username="toadbot"), clock=clock
    )
    router = TelegramRouter(
        client=client,
        recorder=recorder,
        control=bridge,
        target=target,
        self_id=SELF_ID,
        bot_id=BOT_ID,
        clock=clock,
    )
    router.install()
    return router


# --- control bridge ---------------------------------------------------------------------------


async def test_command_reply_replaces_the_command(bridge: ControlBridge) -> None:
    message = OwnMessage(".hello")
    await bridge.handle(message)
    assert message.edits == ["<code>.hello</code>\n\nhi"]


async def test_unknown_command_is_answered_without_editing(bridge: ControlBridge) -> None:
    message = OwnMessage(".todo купити молоко")
    await bridge.handle(message)
    assert message.edits == []
    assert len(message.replies) == 1


@pytest.mark.parametrize(
    "message",
    [
        OwnMessage("просто нотатка"),
        OwnMessage(".hello", out=False),
        OwnMessage(".hello", date=T0 - timedelta(minutes=1)),  # replayed after restart
    ],
)
async def test_ignored_messages(bridge: ControlBridge, message: OwnMessage) -> None:
    await bridge.handle(message)
    assert message.edits == []
    assert message.replies == []


async def test_messages_with_media_are_ignored(bridge: ControlBridge) -> None:
    message = OwnMessage(".hello")
    message.media = object()
    await bridge.handle(message)
    assert message.edits == []


async def test_attachment_is_sent_to_saved_messages(
    bridge: ControlBridge, client: FakeClient
) -> None:
    await bridge.handle(OwnMessage(".report"))
    assert client.sent_files == [
        {
            "entity": "me",
            "name": "r.txt",
            "caption": "📄 r",
            "reply_to": 500,
            "force_document": True,
        }
    ]


async def test_oversized_reply_becomes_a_file(bridge: ControlBridge, client: FakeClient) -> None:
    message = OwnMessage(".big")
    await bridge.handle(message)
    assert "у файлі" in message.edits[0]
    assert client.sent_files[0]["name"] == "reply.html"


# --- router -----------------------------------------------------------------------------------


def _handler(client: FakeClient, name: str) -> Any:
    return next(callback for callback, _ in client.handlers if callback.__name__ == name)


async def test_router_records_bot_and_commands_in_target_chat(
    router: TelegramRouter, client: FakeClient, store: MemoryStore
) -> None:
    on_new = _handler(client, "_on_new_message")
    for message in (
        _chat_message(1, OTHER_ID, "@toadbot На арену"),
        _chat_message(2, BOT_ID, "Победитель Ваба Жаша!"),
        _chat_message(3, OTHER_ID, "всім привіт"),
        _chat_message(4, BOT_ID, "чужий чат", peer=999),
    ):
        await on_new(SimpleNamespace(chat_id=message.chat_id, message=message))

    assert [message.msg_id for message in store.added] == [1, 2]
    assert store.added[1].is_bot


async def test_router_records_edits_and_deletions(
    router: TelegramRouter, client: FakeClient, store: MemoryStore
) -> None:
    edited = _chat_message(2, BOT_ID, "оновлено")
    await _handler(client, "_on_edited")(SimpleNamespace(chat_id=edited.chat_id, message=edited))
    on_deleted = _handler(client, "_on_deleted")
    await on_deleted(SimpleNamespace(chat_id=CHAT_ID, deleted_ids=[1, 2]))
    await on_deleted(SimpleNamespace(chat_id=None, deleted_ids=[3]))
    await on_deleted(SimpleNamespace(chat_id=-100999, deleted_ids=[4]))

    assert store.added[0].event is MessageEvent.EDIT
    assert store.deleted == [(CHAT_ID, [1, 2]), (CHAT_ID, [3])]


async def test_router_sends_saved_messages_to_control(
    router: TelegramRouter, client: FakeClient, store: MemoryStore
) -> None:
    message = OwnMessage(".hello")
    await _handler(client, "_on_new_message")(SimpleNamespace(chat_id=SELF_ID, message=message))
    assert message.edits
    assert store.added == []


async def test_router_does_nothing_without_target_chat(
    router: TelegramRouter, client: FakeClient, store: MemoryStore, target: TargetChat
) -> None:
    target.update(None, None, ChatSource.NONE)
    message = _chat_message(2, BOT_ID, "Жаба инфо")
    await _handler(client, "_on_new_message")(
        SimpleNamespace(chat_id=message.chat_id, message=message)
    )
    await _handler(client, "_on_deleted")(SimpleNamespace(chat_id=CHAT_ID, deleted_ids=[2]))
    assert store.added == []
    assert store.deleted == []
