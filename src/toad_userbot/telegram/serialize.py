"""Conversion of Telethon messages into :class:`RecordedMessage`."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any, Final

from telethon import utils
from telethon.tl import types

from toad_userbot.recorder.models import Button, Entity, JsonScalar, MessageEvent, RecordedMessage

_ENTITY_BASE_KEYS: Final = frozenset({"_", "offset", "length"})
_CAMEL_BOUNDARY = re.compile(r"(?<!^)(?=[A-Z])")


def serialize_message(
    message: types.Message,
    *,
    event: MessageEvent,
    self_id: int,
    bot_id: int,
    received_at: datetime,
) -> RecordedMessage:
    sender_id = _sender_id(message, self_id)
    return RecordedMessage(
        chat_id=int(utils.get_peer_id(message.peer_id)),
        msg_id=int(message.id),
        event=event,
        sender_id=sender_id,
        is_bot=sender_id is not None and sender_id == bot_id,
        is_outgoing=bool(message.out),
        sent_at=_aware(message.date),
        edited_at=_aware(message.edit_date) if message.edit_date else None,
        received_at=received_at,
        reply_to_msg_id=_reply_to(message.reply_to),
        media=_media_kind(message.media),
        text=message.message or "",
        entities=tuple(_entity(entity) for entity in message.entities or ()),
        buttons=_buttons(message.reply_markup),
    )


def _sender_id(message: types.Message, self_id: int) -> int | None:
    if message.from_id is not None:
        return int(utils.get_peer_id(message.from_id))
    return self_id if message.out else None


def _aware(moment: datetime) -> datetime:
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)


def _reply_to(header: Any) -> int | None:
    if isinstance(header, types.MessageReplyHeader) and header.reply_to_msg_id:
        return int(header.reply_to_msg_id)
    return None


def _media_kind(media: Any) -> str | None:
    if media is None or isinstance(media, types.MessageMediaEmpty):
        return None
    return _snake(type(media).__name__.removeprefix("MessageMedia"))


def _entity(entity: Any) -> Entity:
    extra: dict[str, JsonScalar] = {
        key: value
        for key, value in entity.to_dict().items()
        if key not in _ENTITY_BASE_KEYS and isinstance(value, str | int | bool)
    }
    return Entity(
        type=_snake(type(entity).__name__.removeprefix("MessageEntity")),
        offset=int(entity.offset),
        length=int(entity.length),
        extra=extra,
    )


def _buttons(markup: Any) -> tuple[tuple[Button, ...], ...]:
    rows = getattr(markup, "rows", None)
    if not rows:
        return ()
    return tuple(tuple(_button(button) for button in row.buttons) for row in rows)


def _button(button: Any) -> Button:
    """Buttons are ``KeyboardInlineButton``/``KeyboardButton`` with a separate ``type`` object."""
    text = str(getattr(button, "text", ""))
    kind = getattr(button, "type", None)
    if isinstance(kind, types.InlineButtonTypeSwitchInline):
        return Button("switch_inline", text, kind.query)
    if isinstance(kind, types.InlineButtonTypeCallback):
        return Button("callback", text, _decode(kind.data))
    if isinstance(kind, types.InlineButtonTypeUrl):
        return Button("url", text, kind.url)
    if kind is None or isinstance(kind, types.ButtonTypeDefault):
        return Button("text", text)
    name = type(kind).__name__.removeprefix("InlineButtonType").removeprefix("ButtonType")
    return Button(_snake(name), text)


def _decode(data: bytes) -> str:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return "hex:" + data.hex()


def _snake(name: str) -> str:
    return _CAMEL_BOUNDARY.sub("_", name).lower()
