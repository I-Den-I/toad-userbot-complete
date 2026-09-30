from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from pathlib import Path

from tests.fakes import CHAT_ID, OTHER_ID, T0, make_message
from toad_userbot.recorder.models import Button, Entity, MessageEvent
from toad_userbot.storage.db import Database, load_migrations
from toad_userbot.storage.repositories import MessageRepository, MetaRepository


async def test_migrations_are_applied_once(tmp_path: Path) -> None:
    path = tmp_path / "db.sqlite"
    database = Database(path)
    await database.connect()
    version = await database.schema_version()
    await database.close()

    reopened = Database(path)
    await reopened.connect()  # must not fail on already existing tables

    assert version == len(load_migrations()) == await reopened.schema_version()
    await reopened.close()


async def test_add_stats_and_export_round_trip(db: Database) -> None:
    repo = MessageRepository(db)
    rich = replace(
        make_message(msg_id=1, text="Жаба инфо"),
        entities=(Entity("custom_emoji", 0, 2, {"document_id": 5}),),
        buttons=((Button("switch_inline", "С работы", "Завершить работу"),),),
        media="photo",
    )
    await repo.add(rich)
    await repo.add(make_message(msg_id=2, text="@toadbot На арену", sender_id=OTHER_ID))
    await repo.add(make_message(msg_id=1, text="оновлено", event=MessageEvent.EDIT))
    await repo.add(make_message(msg_id=3, received_at=T0 - timedelta(days=2)))

    stats = await repo.stats(now=T0)
    exported = await repo.export_since(T0 - timedelta(hours=1))

    assert (stats.total, stats.from_bot, stats.last_24h) == (4, 3, 3)
    assert stats.last_bot_message_at == T0
    assert [row["msg_id"] for row in exported] == [1, 2, 1]
    first = exported[0]
    assert first["is_bot"] is True
    assert first["media"] == "photo"
    assert first["entities"] == [
        {"type": "custom_emoji", "offset": 0, "length": 2, "extra": {"document_id": 5}}
    ]
    assert first["buttons"] == [
        [{"kind": "switch_inline", "text": "С работы", "payload": "Завершить работу"}]
    ]
    assert first["deleted_at"] is None
    assert exported[2]["event"] == "edit"


async def test_deletions_only_mark_known_messages(db: Database) -> None:
    repo = MessageRepository(db)
    await repo.add(make_message(msg_id=10))
    await repo.add(make_message(msg_id=10, event=MessageEvent.EDIT))
    await repo.add(make_message(msg_id=11))

    first = await repo.mark_deleted(CHAT_ID, [10, 99], T0)
    again = await repo.mark_deleted(CHAT_ID, [10], T0)
    other_chat = await repo.mark_deleted(-100999, [11], T0)
    nothing = await repo.mark_deleted(CHAT_ID, [], T0)

    assert (first, again, other_chat, nothing) == (1, 0, 0, 0)
    exported = await repo.export_since(T0 - timedelta(hours=1))
    assert [row["deleted_at"] is not None for row in exported] == [True, True, False]


async def test_empty_stats(db: Database) -> None:
    stats = await MessageRepository(db).stats(now=T0)
    assert (stats.total, stats.from_bot, stats.last_24h, stats.last_bot_message_at) == (
        0,
        0,
        0,
        None,
    )


async def test_meta_upsert_and_delete(db: Database) -> None:
    meta = MetaRepository(db)
    assert await meta.get("k") is None

    await meta.set("k", "1")
    await meta.set("k", "2")
    assert await meta.get("k") == "2"

    await meta.delete("k")
    assert await meta.get("k") is None
