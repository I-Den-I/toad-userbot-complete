"""Routing of incoming updates. Consumes updates only; never requests anything."""

from __future__ import annotations

from typing import Any

import structlog
from telethon import TelegramClient, events

from toad_userbot.domain.time import Clock
from toad_userbot.recorder.models import MessageEvent
from toad_userbot.recorder.service import Recorder
from toad_userbot.runtime import TargetChat
from toad_userbot.telegram.control_bridge import ControlBridge
from toad_userbot.telegram.serialize import serialize_message

log = structlog.get_logger(__name__)


class TelegramRouter:
    """Saved Messages go to the control plane; the target chat goes to the recorder."""

    def __init__(
        self,
        *,
        client: TelegramClient,
        recorder: Recorder,
        control: ControlBridge,
        target: TargetChat,
        self_id: int,
        bot_id: int,
        clock: Clock,
    ) -> None:
        self._client = client
        self._recorder = recorder
        self._control = control
        self._target = target
        self._self_id = self_id
        self._bot_id = bot_id
        self._clock = clock

    def install(self) -> None:
        self._client.add_event_handler(self._on_new_message, events.NewMessage())
        self._client.add_event_handler(self._on_edited, events.MessageEdited())
        self._client.add_event_handler(self._on_deleted, events.MessageDeleted())

    async def _on_new_message(self, event: Any) -> None:
        if event.chat_id == self._self_id:
            await self._control.handle(event.message)
            return
        await self._record(event.message, MessageEvent.NEW)

    async def _on_edited(self, event: Any) -> None:
        if event.chat_id == self._self_id:
            return
        await self._record(event.message, MessageEvent.EDIT)

    async def _on_deleted(self, event: Any) -> None:
        target = self._target.id
        if target is None:
            return
        # Basic groups report deletions without a chat id; the store only marks ids it knows.
        if event.chat_id is not None and event.chat_id != target:
            return
        try:
            await self._recorder.on_deleted(target, [int(msg_id) for msg_id in event.deleted_ids])
        except Exception:
            log.exception("router.deletion_failed", chat_id=target)

    async def _record(self, message: Any, kind: MessageEvent) -> None:
        if self._target.id is None or message.chat_id != self._target.id:
            return
        try:
            recorded = serialize_message(
                message,
                event=kind,
                self_id=self._self_id,
                bot_id=self._bot_id,
                received_at=self._clock.now(),
            )
            await self._recorder.on_message(recorded)
        except Exception:
            log.exception("router.record_failed", chat_id=message.chat_id, msg_id=message.id)
