"""Mutable process-wide state shared between the wiring layer and control commands."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Final

from toad_userbot.config import Paths
from toad_userbot.domain.time import Clock

# Exit code of a restart requested with ``.restart``. Docker's "unless-stopped" policy (or
# systemd's Restart=always) starts the process again; 75 (EX_TEMPFAIL) makes the intent
# visible in logs and distinguishes it from a clean stop.
EXIT_RESTART: Final = 75

# Meta key under which ``.chat set`` stores the target chat override.
TARGET_CHAT_META_KEY: Final = "target_chat_id"


class ChatSource(StrEnum):
    CONFIG = "config"
    OVERRIDE = "override"
    NONE = "none"


@dataclass(slots=True)
class TargetChat:
    """The one chat the userbot works in. Can be changed at runtime with ``.chat set``."""

    id: int | None = None
    title: str | None = None
    source: ChatSource = ChatSource.NONE

    def update(self, chat_id: int | None, title: str | None, source: ChatSource) -> None:
        self.id = chat_id
        self.title = title
        self.source = source if chat_id is not None else ChatSource.NONE


@dataclass(frozen=True, slots=True)
class BuildInfo:
    version: str
    git_commit: str


@dataclass(frozen=True, slots=True)
class BotIdentity:
    username: str
    id: int


class Shutdown:
    """Single place that decides when and with which exit code the process stops."""

    def __init__(self) -> None:
        self._event = asyncio.Event()
        self.exit_code = 0

    @property
    def requested(self) -> bool:
        return self._event.is_set()

    def request(self, exit_code: int = 0) -> None:
        if not self._event.is_set():
            self.exit_code = exit_code
            self._event.set()

    async def wait(self) -> None:
        await self._event.wait()


@dataclass(frozen=True, slots=True)
class Runtime:
    started_at: datetime
    build: BuildInfo
    paths: Paths
    clock: Clock
    shutdown: Shutdown
    target: TargetChat
    bot: BotIdentity
    config_chat_id: int | None
