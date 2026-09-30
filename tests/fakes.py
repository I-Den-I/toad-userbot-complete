"""Test doubles shared across the suite."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from toad_userbot.control.ports import AccountInfo, ChatInfo
from toad_userbot.recorder.models import MessageEvent, RecordedMessage, RecorderStats

T0 = datetime(2026, 9, 30, 12, 31, tzinfo=UTC)  # 15:31 in game time
BOT_ID = 7_000_000_001
SELF_ID = 42
OTHER_ID = 43
CHAT_ID = -1001234567890


@dataclass
class FakeClock:
    current: datetime = T0

    def now(self) -> datetime:
        return self.current

    def advance(self, **delta: float) -> None:
        self.current += timedelta(**delta)


@dataclass
class FakeTelegram:
    connected: bool = True
    rtt: float = 0.087
    me: AccountInfo = field(default_factory=lambda: AccountInfo(SELF_ID, "Скала", "skala"))
    known_groups: list[ChatInfo] = field(
        default_factory=lambda: [ChatInfo(CHAT_ID, "Болото"), ChatInfo(-100555, "Робочий чат")]
    )

    def is_connected(self) -> bool:
        return self.connected

    async def ping(self) -> float:
        return self.rtt

    async def account(self) -> AccountInfo:
        return self.me

    async def groups(self, query: str | None, limit: int) -> list[ChatInfo]:
        matching = [
            group
            for group in self.known_groups
            if query is None or query.casefold() in group.title.casefold()
        ]
        return matching[:limit]

    async def find_group(self, chat_id: int) -> ChatInfo | None:
        return next((group for group in self.known_groups if group.id == chat_id), None)


@dataclass
class FakeMeta:
    values: dict[str, str] = field(default_factory=dict)

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def set(self, key: str, value: str) -> None:
        self.values[key] = value

    async def delete(self, key: str) -> None:
        self.values.pop(key, None)


@dataclass
class FakeMessageStats:
    rows: list[dict[str, Any]] = field(default_factory=list)
    summary: RecorderStats = field(
        default_factory=lambda: RecorderStats(
            total=10, from_bot=6, last_24h=4, last_bot_message_at=T0 - timedelta(minutes=5)
        )
    )

    async def stats(self, now: datetime) -> RecorderStats:
        return self.summary

    async def export_since(self, since: datetime) -> list[dict[str, Any]]:
        return self.rows


def make_message(
    *,
    msg_id: int = 1,
    text: str = "",
    sender_id: int | None = BOT_ID,
    chat_id: int = CHAT_ID,
    event: MessageEvent = MessageEvent.NEW,
    received_at: datetime = T0,
    is_outgoing: bool = False,
) -> RecordedMessage:
    return RecordedMessage(
        chat_id=chat_id,
        msg_id=msg_id,
        event=event,
        sender_id=sender_id,
        is_bot=sender_id == BOT_ID,
        is_outgoing=is_outgoing,
        sent_at=received_at,
        edited_at=None,
        received_at=received_at,
        reply_to_msg_id=None,
        media=None,
        text=text,
    )
