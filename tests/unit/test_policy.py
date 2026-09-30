from __future__ import annotations

import pytest

from tests.fakes import BOT_ID, OTHER_ID
from toad_userbot.recorder.policy import RecordingPolicy

POLICY = RecordingPolicy(bot_id=BOT_ID, bot_username="toadbot")


@pytest.mark.parametrize(
    "text",
    [
        "@toadbot На арену",
        "@ToadBot Завершить работу",
        "/toad_info@toadbot",
        "/toad_info",
        "Покормить жабу",
        "покормить жабенка",
        "Жаба инфо",
        "Моя семья",
        "Поход в столовую",
        "  Работа крупье",
        "Брак вознаграждение",
    ],
)
def test_commands_addressed_to_the_bot_are_recorded(text: str) -> None:
    assert POLICY.should_record(sender_id=OTHER_ID, text=text)


@pytest.mark.parametrize(
    "text",
    [
        "",
        "   ",
        "привіт усім",
        "жаба сьогодні зла",
        "/start@otherbot",
        "@someone привіт",
        "Моя",  # a bare word is conversation, not "Моя жаба"
    ],
)
def test_ordinary_chat_is_not_recorded(text: str) -> None:
    assert not POLICY.should_record(sender_id=OTHER_ID, text=text)


def test_everything_the_bot_says_is_recorded() -> None:
    assert POLICY.should_record(sender_id=BOT_ID, text="")
    assert POLICY.should_record(sender_id=BOT_ID, text="Победитель Ваба Жаша!")


def test_custom_command_words() -> None:
    policy = RecordingPolicy(bot_id=BOT_ID, bot_username="toadbot", command_words=("квак",))
    assert policy.should_record(sender_id=OTHER_ID, text="Квак квак")
    assert not policy.should_record(sender_id=OTHER_ID, text="Покормить жабу")
