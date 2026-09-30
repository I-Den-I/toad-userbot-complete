"""Interfaces the control commands depend on. Implemented by adapters in other packages."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from toad_userbot.recorder.models import RecorderStats


@dataclass(frozen=True, slots=True)
class AccountInfo:
    id: int
    name: str
    username: str | None


@dataclass(frozen=True, slots=True)
class ChatInfo:
    id: int
    title: str


class TelegramInfo(Protocol):
    def is_connected(self) -> bool: ...

    async def ping(self) -> float:
        """Round-trip time of a no-op API request, in seconds."""
        ...

    async def account(self) -> AccountInfo: ...

    async def groups(self, query: str | None, limit: int) -> list[ChatInfo]: ...

    async def find_group(self, chat_id: int) -> ChatInfo | None: ...


class MessageStats(Protocol):
    async def stats(self, now: datetime) -> RecorderStats: ...

    async def export_since(self, since: datetime) -> list[dict[str, Any]]: ...


class KeyValueStore(Protocol):
    async def get(self, key: str) -> str | None: ...

    async def set(self, key: str, value: str) -> None: ...

    async def delete(self, key: str) -> None: ...
