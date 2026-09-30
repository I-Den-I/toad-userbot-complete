from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from pathlib import Path

import pytest
import structlog

from toad_userbot.logging_setup import configure_logging
from toad_userbot.system.logtail import filter_by_level, tail_lines


@pytest.fixture(autouse=True)
def _restore_logging() -> Iterator[None]:
    root = logging.getLogger()
    handlers, level = root.handlers[:], root.level
    yield
    for handler in root.handlers:
        handler.close()
    root.handlers[:] = handlers
    root.setLevel(level)
    structlog.reset_defaults()


def test_file_log_matches_the_format_logs_command_expects(tmp_path: Path) -> None:
    log_file = tmp_path / "logs" / "userbot.log"
    configure_logging(level="INFO", fmt="console", log_file=log_file)

    log = structlog.get_logger("test")
    log.debug("hidden")
    log.info("recorder.saved", msg_id=1)
    log.error("router.record_failed", msg_id=2)
    logging.getLogger("telethon.network").info("chatty third-party line")
    logging.getLogger("telethon.network").warning("third-party warning")

    lines = tail_lines(log_file, 50)
    text = "\n".join(lines)
    assert "hidden" not in text
    assert "chatty third-party line" not in text
    assert "third-party warning" in text
    errors = filter_by_level(lines, "error")
    assert len(errors) == 1
    assert "router.record_failed" in errors[0]
    assert len(filter_by_level(lines, "info")) == 3


def test_json_stdout(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(level="INFO", fmt="json")

    structlog.get_logger("test").info("app.started", chat_id=-100, name="Болото")

    record = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert record["event"] == "app.started"
    assert record["level"] == "info"
    assert record["name"] == "Болото"
    assert "timestamp" in record
