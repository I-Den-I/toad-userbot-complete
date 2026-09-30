"""Telethon client factory and connection lifecycle.

Stealth rules (docs/ARCHITECTURE.md, §5). @toadbot mutes accounts that look at the chat too
often, so this process must never produce any signal other than the commands it sends:

* no read receipts — never mark anything as read;
* no history polling — updates arrive by themselves, nothing is fetched in loops;
* no online presence — the account status is never set to online;
* no typing indicators.

``tests/test_architecture.py`` fails if any of the corresponding Telethon APIs appear in
``src/``. Catching up after a reconnect uses ``updates.getDifference``, which is not a read.
"""

from __future__ import annotations

import asyncio
import platform
from pathlib import Path
from typing import Any

from telethon import TelegramClient, utils

from toad_userbot.control.ports import AccountInfo


class NotAuthorizedError(Exception):
    """The session file is missing or no longer valid; ``toad-userbot login`` is required."""


def build_client(
    *, session_path: Path, api_id: int, api_hash: str, app_version: str
) -> TelegramClient:
    return TelegramClient(
        str(session_path),
        api_id,
        api_hash,
        device_model="Toad Userbot",
        system_version=platform.system(),
        app_version=app_version,
        catch_up=True,
        flood_sleep_threshold=60,
        connection_retries=10,
        retry_delay=5,
    )


def account_info(user: Any) -> AccountInfo:
    return AccountInfo(
        id=int(user.id),
        name=str(utils.get_display_name(user)),
        username=user.username,
    )


class TelegramConnection:
    """Connects, verifies authorization and reports a permanent disconnect."""

    def __init__(self, client: TelegramClient) -> None:
        self.client = client

    async def open(self) -> AccountInfo:
        await self.client.connect()
        if not await self.client.is_user_authorized():
            raise NotAuthorizedError
        return account_info(await self.client.get_me())

    async def resolve_user_id(self, username: str) -> int:
        entity = await self.client.get_input_entity(username)
        return int(utils.get_peer_id(entity))

    async def wait_disconnected(self) -> None:
        await asyncio.shield(self.client.disconnected)

    async def close(self) -> None:
        if self.client.is_connected():
            await self.client.disconnect()
