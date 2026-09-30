from __future__ import annotations

from datetime import timedelta

from tests.fakes import BOT_ID, CHAT_ID, OTHER_ID, SELF_ID, T0, FakeClock, make_message
from toad_userbot.recorder.policy import RecordingPolicy
from toad_userbot.recorder.service import Recorder
from toad_userbot.storage.db import Database
from toad_userbot.storage.repositories import MessageRepository


def _recorder(db: Database, clock: FakeClock, *, enabled: bool = True) -> Recorder:
    return Recorder(
        store=MessageRepository(db),
        policy=RecordingPolicy(bot_id=BOT_ID, bot_username="toadbot"),
        clock=clock,
        enabled=enabled,
    )


async def test_screenshot_scenario_is_recorded_without_chatter(
    db: Database, clock: FakeClock
) -> None:
    """Replays the traffic from the owner's screenshots, with small talk mixed in."""
    recorder = _recorder(db, clock)
    traffic = [
        make_message(msg_id=1, sender_id=OTHER_ID, text="@toadbot На арену"),
        make_message(msg_id=2, text="Победитель Ваба Жаша!"),
        make_message(msg_id=3, sender_id=SELF_ID, text="/toad_info@toadbot", is_outgoing=True),
        make_message(msg_id=4, text="💼: Завершай работу"),
        make_message(msg_id=5, sender_id=OTHER_ID, text="хто на тусу ввечері?"),
        make_message(msg_id=6, sender_id=SELF_ID, text="@toadbot Завершить работу"),
        make_message(msg_id=7, text="Твоя жаба бежала с работы домой"),
    ]

    stored = [await recorder.on_message(message) for message in traffic]
    clock.advance(minutes=5)
    await recorder.on_deleted(CHAT_ID, [1, 2, 3, 4, 5])

    assert stored == [True, True, True, True, False, True, True]
    assert recorder.counters.recorded == 6
    assert recorder.counters.recorded_from_bot == 3
    assert recorder.counters.last_bot_message_at == T0
    assert recorder.counters.deletions == 4  # message 5 was never stored

    stats = await MessageRepository(db).stats(now=clock.now())
    assert (stats.total, stats.from_bot) == (6, 3)


async def test_disabled_recorder_stores_nothing(db: Database, clock: FakeClock) -> None:
    recorder = _recorder(db, clock, enabled=False)

    assert not await recorder.on_message(make_message(text="Жаба инфо"))
    await recorder.on_deleted(CHAT_ID, [1])

    stats = await MessageRepository(db).stats(now=clock.now() + timedelta(seconds=1))
    assert stats.total == 0
    assert recorder.counters.recorded == 0
