"""Built-in control commands."""

from __future__ import annotations

from dataclasses import dataclass

from toad_userbot.control.ports import KeyValueStore, MessageStats, TelegramInfo
from toad_userbot.control.registry import Command, CommandRegistry
from toad_userbot.recorder.service import Recorder
from toad_userbot.runtime import Runtime


@dataclass(frozen=True, slots=True)
class CommandDeps:
    runtime: Runtime
    telegram: TelegramInfo
    recorder: Recorder
    messages: MessageStats
    meta: KeyValueStore
    registry: CommandRegistry
    prefix: str


def build_commands(deps: CommandDeps) -> list[Command]:
    # Imported here to keep the package import graph acyclic (the modules import CommandDeps).
    from toad_userbot.control.commands import general, host, recording  # noqa: PLC0415

    return [*general.build(deps), *host.build(deps), *recording.build(deps)]
