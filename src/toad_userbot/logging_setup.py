"""Logging configuration.

structlog renders through the standard library so third-party logs (Telethon, aiosqlite) share
the same handlers:

* stdout — JSON in production, human-readable in development;
* rotating file — always human-readable; the ``.logs`` control command tails it.
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

import structlog
from structlog.typing import Processor

from toad_userbot.config import LogFormat, LogLevel

_NOISY_LOGGERS = ("telethon", "aiosqlite", "asyncio")


def configure_logging(
    *,
    level: LogLevel,
    fmt: LogFormat,
    log_file: Path | None = None,
    max_bytes: int = 5_000_000,
    backups: int = 3,
) -> None:
    shared: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
    ]
    structlog.configure(
        processors=[*shared, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    stdout_renderer: Processor
    if fmt == "json":
        stdout_renderer = structlog.processors.JSONRenderer(ensure_ascii=False)
        stdout_chain: list[Processor] = [structlog.processors.dict_tracebacks, stdout_renderer]
    else:
        stdout_renderer = structlog.dev.ConsoleRenderer(colors=sys.stdout.isatty())
        stdout_chain = [stdout_renderer]

    handlers: list[logging.Handler] = [
        _handler(logging.StreamHandler(sys.stdout), shared, stdout_chain),
    ]
    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            log_file, maxBytes=max_bytes, backupCount=backups, encoding="utf-8"
        )
        handlers.append(
            _handler(file_handler, shared, [structlog.dev.ConsoleRenderer(colors=False)])
        )

    root = logging.getLogger()
    root.handlers.clear()
    for handler in handlers:
        root.addHandler(handler)
    root.setLevel(level)

    third_party_level = max(logging.WARNING, logging.getLevelNamesMapping()[level])
    for name in _NOISY_LOGGERS:
        logging.getLogger(name).setLevel(third_party_level)


def _handler(
    handler: logging.Handler, shared: list[Processor], chain: list[Processor]
) -> logging.Handler:
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=shared,
            processors=[structlog.stdlib.ProcessorFormatter.remove_processors_meta, *chain],
        )
    )
    return handler
