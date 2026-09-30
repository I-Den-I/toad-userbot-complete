"""Command model and registry."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime


class UsageError(Exception):
    """Raised by a handler when its arguments are invalid. The message is shown to the owner."""


@dataclass(frozen=True, slots=True)
class Attachment:
    filename: str
    content: bytes
    caption: str = ""


@dataclass(frozen=True, slots=True)
class CommandResult:
    """Reply to a command.

    ``html`` replaces the command message (or is sent as a separate reply when
    ``edit_original`` is false). ``after_reply`` runs once the reply has been delivered.
    """

    html: str
    attachment: Attachment | None = None
    edit_original: bool = True
    after_reply: Callable[[], None] | None = None


@dataclass(frozen=True, slots=True)
class CommandContext:
    name: str
    args: tuple[str, ...]
    sent_at: datetime
    received_at: datetime


Handler = Callable[[CommandContext], Awaitable[CommandResult]]


@dataclass(frozen=True, slots=True)
class Command:
    name: str
    group: str
    summary: str
    handler: Handler
    usage: str = ""
    aliases: tuple[str, ...] = ()


class CommandRegistry:
    def __init__(self) -> None:
        self._by_name: dict[str, Command] = {}
        self._ordered: list[Command] = []

    def register(self, command: Command) -> None:
        for name in (command.name, *command.aliases):
            if name in self._by_name:
                msg = f"command name {name!r} is already registered"
                raise ValueError(msg)
        for name in (command.name, *command.aliases):
            self._by_name[name] = command
        self._ordered.append(command)

    def register_all(self, commands: list[Command]) -> None:
        for command in commands:
            self.register(command)

    def resolve(self, name: str) -> Command | None:
        return self._by_name.get(name)

    def commands(self) -> tuple[Command, ...]:
        return tuple(self._ordered)
