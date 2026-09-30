"""Executes owner commands from Saved Messages and delivers the replies."""

from __future__ import annotations

import io
from datetime import datetime, timedelta
from typing import Any, Final

import structlog
from telethon import TelegramClient

from toad_userbot.control.dispatcher import ControlDispatcher
from toad_userbot.control.registry import Attachment, CommandResult
from toad_userbot.domain.time import Clock

log = structlog.get_logger(__name__)

# Commands older than process start are replayed by catch-up after a restart; running them
# again could, for example, loop ``.restart`` forever.
STALE_GRACE: Final = timedelta(seconds=10)
MESSAGE_LIMIT: Final = 4000


class ControlBridge:
    def __init__(
        self,
        *,
        client: TelegramClient,
        dispatcher: ControlDispatcher,
        clock: Clock,
        started_at: datetime,
    ) -> None:
        self._client = client
        self._dispatcher = dispatcher
        self._clock = clock
        self._started_at = started_at

    async def handle(self, message: Any) -> None:
        # Only plain text typed by the owner; files we send ourselves carry media.
        if not message.out or message.media is not None or message.fwd_from is not None:
            return
        parsed = self._dispatcher.parse(message.message or "")
        if parsed is None:
            return
        if message.date < self._started_at - STALE_GRACE:
            log.info("control.stale_command_skipped", command=parsed.name, sent_at=message.date)
            return

        result = await self._dispatcher.dispatch(
            parsed, sent_at=message.date, received_at=self._clock.now()
        )
        try:
            await self._deliver(message, result)
        except Exception:
            log.exception("control.delivery_failed", command=parsed.name)
        if result.after_reply is not None:
            result.after_reply()

    async def _deliver(self, message: Any, result: CommandResult) -> None:
        text, attachment = result.html, result.attachment
        if len(text) > MESSAGE_LIMIT:
            attachment = Attachment("reply.html", text.encode("utf-8"), "📄 Повна відповідь")
            text = "📄 Відповідь задовга для повідомлення — у файлі нижче."

        if result.edit_original:
            await message.edit(text, parse_mode="html", link_preview=False)
        else:
            await message.reply(text, parse_mode="html", link_preview=False)

        if attachment is not None:
            payload = io.BytesIO(attachment.content)
            payload.name = attachment.filename
            await self._client.send_file(
                "me",
                payload,
                caption=attachment.caption,
                reply_to=message.id,
                force_document=True,
            )
