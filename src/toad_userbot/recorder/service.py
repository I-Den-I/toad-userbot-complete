"""Recorder: stores bot traffic of the target chat as soon as it arrives.

The bot deletes commands and replies after about five minutes, so recording must happen on
receipt. The recorder never talks to Telegram; it only consumes already received updates.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

import structlog

from toad_userbot.domain.time import Clock
from toad_userbot.recorder.models import RecordedMessage
from toad_userbot.recorder.policy import RecordingPolicy

log = structlog.get_logger(__name__)


class MessageStore(Protocol):
    async def add(self, message: RecordedMessage) -> None: ...

    async def mark_deleted(self, chat_id: int, msg_ids: Sequence[int], at: datetime) -> int: ...


@dataclass(slots=True)
class SessionCounters:
    recorded: int = 0
    recorded_from_bot: int = 0
    deletions: int = 0
    last_bot_message_at: datetime | None = None


class Recorder:
    def __init__(
        self,
        *,
        store: MessageStore,
        policy: RecordingPolicy,
        clock: Clock,
        enabled: bool = True,
    ) -> None:
        self._store = store
        self._policy = policy
        self._clock = clock
        self.enabled = enabled
        self.counters = SessionCounters()

    @property
    def policy(self) -> RecordingPolicy:
        return self._policy

    async def on_message(self, message: RecordedMessage) -> bool:
        """Store the message if the policy says so. Returns whether it was stored."""
        if not self.enabled:
            return False
        if not self._policy.should_record(sender_id=message.sender_id, text=message.text):
            return False

        await self._store.add(message)
        self.counters.recorded += 1
        if message.is_bot:
            self.counters.recorded_from_bot += 1
            self.counters.last_bot_message_at = message.received_at

        log.debug(
            "recorder.saved",
            chat_id=message.chat_id,
            msg_id=message.msg_id,
            kind=message.event.value,
            is_bot=message.is_bot,
            preview=message.text[:60],
        )
        return True

    async def on_deleted(self, chat_id: int, msg_ids: Sequence[int]) -> None:
        """Mark recorded messages as deleted. Unknown ids are ignored by the store."""
        if not self.enabled or not msg_ids:
            return
        matched = await self._store.mark_deleted(chat_id, msg_ids, self._clock.now())
        self.counters.deletions += matched
        if matched:
            log.debug("recorder.deleted", chat_id=chat_id, count=matched)
