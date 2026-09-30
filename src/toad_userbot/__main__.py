"""Command-line entry point: ``toad-userbot [run|login|healthcheck]``."""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Sequence
from typing import Final

from pydantic import ValidationError

from toad_userbot import __version__
from toad_userbot.config import ConfigError, RuntimeSettings, Settings, load_app_config
from toad_userbot.logging_setup import configure_logging
from toad_userbot.system.heartbeat import is_alive

EXIT_CONFIG: Final = 78  # EX_CONFIG
HEALTHCHECK_MAX_AGE: Final = 120.0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="toad-userbot", description="Юзербот для гри @toadbot в одному чаті."
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command")
    commands.add_parser("run", help="запустити юзербота (типово)")
    commands.add_parser("login", help="увійти в акаунт і зберегти сесію")
    healthcheck = commands.add_parser("healthcheck", help="перевірка живості для Docker")
    healthcheck.add_argument(
        "--max-age",
        type=float,
        default=HEALTHCHECK_MAX_AGE,
        help="максимальний вік heartbeat-файлу в секундах",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    command = args.command or "run"

    if command == "healthcheck":
        return 0 if is_alive(RuntimeSettings().paths.heartbeat, args.max_age) else 1

    try:
        settings = Settings()
        config = load_app_config(settings.config_path)
    except (ValidationError, ConfigError) as exc:
        print(f"Помилка конфігурації:\n{exc}", file=sys.stderr)
        return EXIT_CONFIG

    if command == "login":
        configure_logging(level="WARNING", fmt="console")
        from toad_userbot.telegram.login import login  # noqa: PLC0415 - only needed here

        return asyncio.run(login(settings))

    settings.paths.ensure()
    configure_logging(
        level=settings.log_level,
        fmt=settings.log_format,
        log_file=settings.paths.log_file,
        max_bytes=config.log_file.max_bytes,
        backups=config.log_file.backups,
    )
    from toad_userbot.app import run  # noqa: PLC0415 - keeps `healthcheck` import-light

    return asyncio.run(run(settings, config))


if __name__ == "__main__":
    sys.exit(main())
