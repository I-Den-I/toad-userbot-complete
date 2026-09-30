"""Decides which chat messages are worth recording.

Only the bot's own messages and messages addressed to the bot are stored. Ordinary
conversation in the chat is ignored: it is irrelevant to the game and private to its authors.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

# First words of game commands, casefolded. A message that starts with one of them is treated as
# a command even without the ``@toadbot`` prefix, because the bot accepts both forms.
DEFAULT_COMMAND_WORDS: Final[tuple[str, ...]] = (
    "арена",
    "брак",
    "взять",
    "выбрать",
    "выйти",
    "где жаба",
    "дать банде",
    "дать жабе",
    "дать жабенку",
    "дейли",
    "дуэль",
    "ежедневные",
    "жаба дня",
    "жаба инфо",
    "жабу на тусу",
    "забег",
    "забрать",
    "завершить",
    "использовать",
    "клан",
    "кмн",
    "конвертировать",
    "купить",
    "мое ",
    "мои ",
    "мой ",
    "моя ",
    "моё ",
    "на арену",
    "напасть",
    "начать",
    "откормить",
    "отправить",
    "отправиться",
    "подарить",
    "покинуть",
    "покормить",
    "получить",
    "поход в столовую",
    "починить",
    "приобрести",
    "работа ",
    "реанимировать",
    "рейд",
    "рулетка",
    "сделать подарок",
    "скрафтить",
    "снаряжение",
    "собрать",
    "соревнование",
    "топ ",
    "туса",
)


@dataclass(frozen=True, slots=True)
class RecordingPolicy:
    bot_id: int
    bot_username: str
    command_words: tuple[str, ...] = DEFAULT_COMMAND_WORDS

    def should_record(self, *, sender_id: int | None, text: str) -> bool:
        """Record everything the bot says and every command addressed to it."""
        return sender_id == self.bot_id or self.is_bot_command(text)

    def is_bot_command(self, text: str) -> bool:
        normalized = text.strip().casefold()
        if not normalized:
            return False

        mention = f"@{self.bot_username}"
        if normalized.startswith(mention):
            return True

        if normalized.startswith("/"):
            first_token = normalized.split(maxsplit=1)[0]
            # "/cmd@otherbot" is addressed to a different bot.
            return "@" not in first_token or first_token.endswith(mention)

        return normalized.startswith(self.command_words)
