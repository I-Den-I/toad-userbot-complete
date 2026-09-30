"""Transport-independent representation of a chat message."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

JsonScalar = str | int | bool


class MessageEvent(StrEnum):
    NEW = "new"
    EDIT = "edit"


@dataclass(frozen=True, slots=True)
class Entity:
    """Formatting entity. Offsets and lengths are in UTF-16 code units, as Telegram sends them."""

    type: str
    offset: int
    length: int
    extra: Mapping[str, JsonScalar] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Button:
    """Keyboard button. ``payload`` is the inline query, callback data or URL, if any."""

    kind: str
    text: str
    payload: str | None = None


@dataclass(frozen=True, slots=True)
class RecordedMessage:
    chat_id: int
    msg_id: int
    event: MessageEvent
    sender_id: int | None
    is_bot: bool
    is_outgoing: bool
    sent_at: datetime
    edited_at: datetime | None
    received_at: datetime
    reply_to_msg_id: int | None
    media: str | None
    text: str
    entities: tuple[Entity, ...] = ()
    buttons: tuple[tuple[Button, ...], ...] = ()


@dataclass(frozen=True, slots=True)
class RecorderStats:
    total: int
    from_bot: int
    last_24h: int
    last_bot_message_at: datetime | None
