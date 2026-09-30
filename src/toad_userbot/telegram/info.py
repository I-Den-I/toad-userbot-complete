"""Read-only account introspection for control commands.

Listing dialogs does not mark anything as read, and it only runs on an explicit owner command
(``.chats``, ``.chat set``) or once at startup.
"""

from __future__ import annotations

import secrets
import time

from telethon import TelegramClient
from telethon.tl import functions

from toad_userbot.control.ports import AccountInfo, ChatInfo
from toad_userbot.telegram.client import account_info


class TelethonInfo:
    def __init__(self, client: TelegramClient) -> None:
        self._client = client

    def is_connected(self) -> bool:
        return bool(self._client.is_connected())

    async def ping(self) -> float:
        started = time.perf_counter()
        await self._client(functions.PingRequest(ping_id=secrets.randbits(63)))
        return time.perf_counter() - started

    async def account(self) -> AccountInfo:
        return account_info(await self._client.get_me())

    async def groups(self, query: str | None, limit: int) -> list[ChatInfo]:
        needle = query.casefold() if query else None
        found: list[ChatInfo] = []
        async for dialog in self._client.iter_dialogs():
            if not dialog.is_group:
                continue
            title = str(dialog.name or "")
            if needle is not None and needle not in title.casefold():
                continue
            found.append(ChatInfo(id=int(dialog.id), title=title))
            if len(found) >= limit:
                break
        return found

    async def find_group(self, chat_id: int) -> ChatInfo | None:
        async for dialog in self._client.iter_dialogs():
            if dialog.is_group and int(dialog.id) == chat_id:
                return ChatInfo(id=chat_id, title=str(dialog.name or ""))
        return None
