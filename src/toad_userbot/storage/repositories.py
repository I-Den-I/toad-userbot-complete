"""Repositories: the only place that knows the table layout."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import asdict
from datetime import datetime, timedelta
from typing import Any

from toad_userbot.recorder.models import Button, Entity, RecordedMessage, RecorderStats
from toad_userbot.storage.db import Database


def _iso(moment: datetime | None) -> str | None:
    return moment.isoformat() if moment is not None else None


def _parse_iso(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value is not None else None


def _entities_json(entities: Sequence[Entity]) -> str:
    return json.dumps([asdict(entity) for entity in entities], ensure_ascii=False)


def _buttons_json(rows: Sequence[Sequence[Button]]) -> str:
    return json.dumps([[asdict(button) for button in row] for row in rows], ensure_ascii=False)


class MessageRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def add(self, message: RecordedMessage) -> None:
        await self._db.conn.execute(
            """
            INSERT INTO messages (
                chat_id, msg_id, event, sender_id, is_bot, is_outgoing,
                sent_at, edited_at, received_at, reply_to_msg_id, media,
                text, entities, buttons
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                message.chat_id,
                message.msg_id,
                message.event.value,
                message.sender_id,
                int(message.is_bot),
                int(message.is_outgoing),
                _iso(message.sent_at),
                _iso(message.edited_at),
                _iso(message.received_at),
                message.reply_to_msg_id,
                message.media,
                message.text,
                _entities_json(message.entities),
                _buttons_json(message.buttons),
            ),
        )
        await self._db.conn.commit()

    async def mark_deleted(self, chat_id: int, msg_ids: Sequence[int], at: datetime) -> int:
        """Record deletion of messages we have stored. Returns the number of newly marked ids."""
        if not msg_ids:
            return 0
        placeholders = ", ".join("?" for _ in msg_ids)
        cursor = await self._db.conn.execute(
            f"""
            INSERT OR IGNORE INTO deletions (chat_id, msg_id, deleted_at)
            SELECT DISTINCT chat_id, msg_id, ?
            FROM messages
            WHERE chat_id = ? AND msg_id IN ({placeholders})
            """,  # noqa: S608 - placeholders are generated "?" markers, values are bound
            (at.isoformat(), chat_id, *msg_ids),
        )
        await self._db.conn.commit()
        return cursor.rowcount

    async def stats(self, now: datetime) -> RecorderStats:
        day_ago = (now - timedelta(days=1)).isoformat()
        async with self._db.conn.execute(
            """
            SELECT
                COUNT(*),
                COALESCE(SUM(is_bot), 0),
                COALESCE(SUM(received_at >= ?), 0),
                MAX(CASE WHEN is_bot = 1 THEN received_at END)
            FROM messages
            """,
            (day_ago,),
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:  # pragma: no cover - an aggregate query always returns one row
            msg = "stats query returned no rows"
            raise RuntimeError(msg)
        return RecorderStats(
            total=int(row[0]),
            from_bot=int(row[1]),
            last_24h=int(row[2]),
            last_bot_message_at=_parse_iso(row[3]),
        )

    async def export_since(self, since: datetime) -> list[dict[str, Any]]:
        """Messages received since ``since``, oldest first, with deletion time if known."""
        async with self._db.conn.execute(
            """
            SELECT m.*, d.deleted_at
            FROM messages AS m
            LEFT JOIN deletions AS d ON d.chat_id = m.chat_id AND d.msg_id = m.msg_id
            WHERE m.received_at >= ?
            ORDER BY m.id
            """,
            (since.isoformat(),),
        ) as cursor:
            rows = await cursor.fetchall()

        exported: list[dict[str, Any]] = []
        for row in rows:
            record = dict(row)
            record["is_bot"] = bool(record["is_bot"])
            record["is_outgoing"] = bool(record["is_outgoing"])
            record["entities"] = json.loads(record["entities"])
            record["buttons"] = json.loads(record["buttons"])
            exported.append(record)
        return exported


class MetaRepository:
    """Small persistent key/value store for runtime state (cached ids, overrides)."""

    def __init__(self, db: Database) -> None:
        self._db = db

    async def get(self, key: str) -> str | None:
        async with self._db.conn.execute("SELECT value FROM meta WHERE key = ?", (key,)) as cursor:
            row = await cursor.fetchone()
        return str(row[0]) if row else None

    async def set(self, key: str, value: str) -> None:
        await self._db.conn.execute(
            "INSERT INTO meta (key, value) VALUES (?, ?) "
            "ON CONFLICT (key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        await self._db.conn.commit()

    async def delete(self, key: str) -> None:
        await self._db.conn.execute("DELETE FROM meta WHERE key = ?", (key,))
        await self._db.conn.commit()
