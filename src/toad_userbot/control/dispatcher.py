"""Runs parsed commands and turns failures into readable replies."""

from __future__ import annotations

import time
from dataclasses import replace
from datetime import datetime

import structlog

from toad_userbot.control.format import code, esc
from toad_userbot.control.parser import ParsedCommand, parse_command
from toad_userbot.control.registry import CommandContext, CommandRegistry, CommandResult, UsageError

log = structlog.get_logger(__name__)


class ControlDispatcher:
    def __init__(self, registry: CommandRegistry, prefix: str) -> None:
        self._registry = registry
        self.prefix = prefix

    def parse(self, text: str) -> ParsedCommand | None:
        return parse_command(text, self.prefix)

    async def dispatch(
        self, parsed: ParsedCommand, *, sent_at: datetime, received_at: datetime
    ) -> CommandResult:
        command = self._registry.resolve(parsed.name)
        if command is None:
            # Sent as a separate reply: the original message may be an ordinary note.
            return CommandResult(
                html=(
                    f"❓ Невідома команда {code(self.prefix + parsed.name)}. "
                    f"Список команд: {code(self.prefix + 'help')}"
                ),
                edit_original=False,
            )

        context = CommandContext(
            name=command.name, args=parsed.args, sent_at=sent_at, received_at=received_at
        )
        started = time.perf_counter()
        try:
            result = await command.handler(context)
        except UsageError as exc:
            usage = f"{self.prefix}{command.name} {command.usage}".strip()
            result = CommandResult(html=f"⚠️ {esc(exc)}\nВикористання: {code(usage)}")
        except Exception:
            log.exception("control.command_failed", command=command.name, args=parsed.args)
            result = CommandResult(
                html=(
                    f"💥 Помилка під час {code(self.prefix + command.name)}. "
                    f"Деталі: {code(self.prefix + 'logs 20 error')}"
                )
            )
        else:
            log.info(
                "control.command",
                command=command.name,
                args=parsed.args,
                duration_ms=round((time.perf_counter() - started) * 1000),
            )

        if result.edit_original:
            echo = " ".join((self.prefix + command.name, *parsed.args))
            result = replace(result, html=f"{code(echo)}\n\n{result.html}")
        return result
