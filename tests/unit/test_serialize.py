"""Serialization is tested against real Telethon TL objects: the schema changes between
Telethon releases, and the adapter is typed as ``Any``, so only tests can catch drift."""

from __future__ import annotations

from datetime import UTC, datetime

from telethon.tl import types

from tests.fakes import BOT_ID, CHAT_ID, OTHER_ID, SELF_ID, T0
from toad_userbot.recorder.models import Button, MessageEvent, RecordedMessage
from toad_userbot.telegram.serialize import serialize_message

CHANNEL_ID = 1234567890  # CHAT_ID without the -100 prefix
INFO_TEXT = "💼: Завершай работу\n🍰: Покормить можно через 5 ч:34 мин."


def _serialize(message: types.Message, event: MessageEvent = MessageEvent.NEW) -> RecordedMessage:
    return serialize_message(message, event=event, self_id=SELF_ID, bot_id=BOT_ID, received_at=T0)


def _inline(text: str, kind: object) -> types.KeyboardInlineButton:
    return types.KeyboardInlineButton(text=text, type=kind)


def test_bot_info_message_with_custom_emoji_and_switch_inline_buttons() -> None:
    message = types.Message(
        id=100,
        peer_id=types.PeerChannel(CHANNEL_ID),
        from_id=types.PeerUser(BOT_ID),
        date=T0,
        message=INFO_TEXT,
        entities=[
            types.MessageEntityCustomEmoji(offset=0, length=2, document_id=5_555),
            types.MessageEntityBold(offset=4, length=7),
        ],
        reply_markup=types.ReplyInlineMarkup(
            rows=[
                types.KeyboardInlineButtonRow(
                    buttons=[
                        _inline(
                            "🏃 С работы",
                            types.InlineButtonTypeSwitchInline("Завершить работу", same_peer=True),
                        ),
                        _inline(
                            "⚔️ На арену",
                            types.InlineButtonTypeSwitchInline("На арену", same_peer=True),
                        ),
                    ]
                ),
                types.KeyboardInlineButtonRow(
                    buttons=[_inline("🐸 Моя жаба", types.InlineButtonTypeSwitchInline("Моя жаба"))]
                ),
            ]
        ),
    )

    recorded = _serialize(message)

    assert recorded.chat_id == CHAT_ID
    assert recorded.msg_id == 100
    assert recorded.sender_id == BOT_ID
    assert recorded.is_bot
    assert not recorded.is_outgoing
    assert recorded.text == INFO_TEXT
    assert recorded.sent_at == T0
    assert recorded.media is None
    assert [entity.type for entity in recorded.entities] == ["custom_emoji", "bold"]
    assert recorded.entities[0].extra == {"document_id": 5_555}
    assert recorded.entities[1].extra == {}
    assert recorded.buttons == (
        (
            Button("switch_inline", "🏃 С работы", "Завершить работу"),
            Button("switch_inline", "⚔️ На арену", "На арену"),
        ),
        (Button("switch_inline", "🐸 Моя жаба", "Моя жаба"),),
    )


def test_button_kinds() -> None:
    message = types.Message(
        id=1,
        peer_id=types.PeerChannel(CHANNEL_ID),
        from_id=types.PeerUser(BOT_ID),
        date=T0,
        message="",
        reply_markup=types.ReplyInlineMarkup(
            rows=[
                types.KeyboardInlineButtonRow(
                    buttons=[
                        _inline("cb", types.InlineButtonTypeCallback(data=b"roulette:red")),
                        _inline("bin", types.InlineButtonTypeCallback(data=b"\xff\x00")),
                        _inline("url", types.InlineButtonTypeUrl(url="https://toadbot.info")),
                        _inline("copy", types.InlineButtonTypeCopy(copy_text="x")),
                    ]
                )
            ]
        ),
    )

    (row,) = _serialize(message).buttons

    assert row == (
        Button("callback", "cb", "roulette:red"),
        Button("callback", "bin", "hex:ff00"),
        Button("url", "url", "https://toadbot.info"),
        Button("copy", "copy", None),
    )


def test_reply_keyboard_buttons() -> None:
    message = types.Message(
        id=1,
        peer_id=types.PeerChannel(CHANNEL_ID),
        from_id=types.PeerUser(BOT_ID),
        date=T0,
        message="",
        reply_markup=types.ReplyKeyboardMarkup(
            rows=[
                types.KeyboardButtonRow(
                    buttons=[types.KeyboardButton(text="Покормить", type=types.ButtonTypeDefault())]
                )
            ]
        ),
    )

    assert _serialize(message).buttons == ((Button("text", "Покормить"),),)


def test_photo_caption_reply_and_edit() -> None:
    edited = datetime(2026, 9, 30, 12, 32, tzinfo=UTC)
    message = types.Message(
        id=7,
        peer_id=types.PeerChannel(CHANNEL_ID),
        from_id=types.PeerUser(BOT_ID),
        date=T0,
        edit_date=edited,
        message="Жабуля ушла работать в столовую!",
        media=types.MessageMediaPhoto(),
        reply_to=types.MessageReplyHeader(reply_to_msg_id=6),
    )

    recorded = _serialize(message, MessageEvent.EDIT)

    assert recorded.event is MessageEvent.EDIT
    assert recorded.media == "photo"
    assert recorded.reply_to_msg_id == 6
    assert recorded.edited_at == edited
    assert recorded.buttons == ()


def test_outgoing_message_without_from_id_is_attributed_to_self() -> None:
    message = types.Message(
        id=8, peer_id=types.PeerChannel(CHANNEL_ID), date=T0, message="@toadbot На арену", out=True
    )

    recorded = _serialize(message)

    assert recorded.sender_id == SELF_ID
    assert recorded.is_outgoing
    assert not recorded.is_bot


def test_other_member_message() -> None:
    message = types.Message(
        id=9,
        peer_id=types.PeerChannel(CHANNEL_ID),
        from_id=types.PeerUser(OTHER_ID),
        date=T0,
        message=None,
        media=types.MessageMediaEmpty(),
    )

    recorded = _serialize(message)

    assert recorded.sender_id == OTHER_ID
    assert recorded.text == ""
    assert recorded.media is None
