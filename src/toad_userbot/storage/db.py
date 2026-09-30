"""Database connection and schema migrations.

Migrations are plain SQL files in ``migrations/`` named ``NNNN_description.sql``. The applied
version is tracked in ``PRAGMA user_version``; each file runs in its own transaction.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from importlib import resources
from pathlib import Path

import aiosqlite
import structlog

log = structlog.get_logger(__name__)

_MIGRATION_NAME = re.compile(r"^(?P<version>\d{4})_[a-z0-9_]+\.sql$")


@dataclass(frozen=True, slots=True)
class Migration:
    version: int
    name: str
    sql: str


def load_migrations() -> list[Migration]:
    """Read bundled migrations, ordered by version."""
    migrations: list[Migration] = []
    for entry in resources.files("toad_userbot.storage").joinpath("migrations").iterdir():
        match = _MIGRATION_NAME.match(entry.name)
        if match is None:
            continue
        version = int(match["version"])
        migrations.append(Migration(version, entry.name, entry.read_text(encoding="utf-8")))
    migrations.sort(key=lambda migration: migration.version)

    versions = [migration.version for migration in migrations]
    if versions != list(range(1, len(versions) + 1)):
        msg = f"migration versions must be contiguous from 1, got {versions}"
        raise RuntimeError(msg)
    return migrations


class Database:
    """Owns the single SQLite connection of the process."""

    def __init__(self, path: Path | str) -> None:
        self._path = str(path)
        self._conn: aiosqlite.Connection | None = None

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            msg = "database is not connected"
            raise RuntimeError(msg)
        return self._conn

    async def connect(self) -> None:
        self._conn = await aiosqlite.connect(self._path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA journal_mode = WAL")
        await self._conn.execute("PRAGMA foreign_keys = ON")
        await self._conn.execute("PRAGMA busy_timeout = 5000")
        await self.migrate()

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    async def schema_version(self) -> int:
        async with self.conn.execute("PRAGMA user_version") as cursor:
            row = await cursor.fetchone()
        return int(row[0]) if row else 0

    async def migrate(self) -> None:
        current = await self.schema_version()
        for migration in load_migrations():
            if migration.version <= current:
                continue
            # executescript() commits any pending transaction first, so the explicit
            # BEGIN/COMMIT makes the whole file (and the version bump) atomic.
            await self.conn.executescript(
                f"BEGIN;\n{migration.sql}\nPRAGMA user_version = {migration.version};\nCOMMIT;"
            )
            log.info("db.migrated", version=migration.version, name=migration.name)
