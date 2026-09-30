from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from tests.fakes import FakeClock
from toad_userbot.storage.db import Database


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
async def db(tmp_path: Path) -> AsyncIterator[Database]:
    database = Database(tmp_path / "test.db")
    await database.connect()
    yield database
    await database.close()
