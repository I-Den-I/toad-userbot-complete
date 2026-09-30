"""General commands: help, ping, uptime, version, restart."""

from __future__ import annotations

from typing import TYPE_CHECKING

from toad_userbot.control.format import code, esc, game_time, human_duration
from toad_userbot.control.registry import Command, CommandContext, CommandResult
from toad_userbot.runtime import EXIT_RESTART
from toad_userbot.system.metrics import host_info

if TYPE_CHECKING:
    from toad_userbot.control.commands import CommandDeps

GROUP = "Загальні"


def build(deps: CommandDeps) -> list[Command]:
    runtime = deps.runtime

    async def help_command(_: CommandContext) -> CommandResult:
        lines = [f"<b>Команди</b> (префікс {code(deps.prefix)})"]
        current_group: str | None = None
        for command in deps.registry.commands():
            if command.group != current_group:
                current_group = command.group
                lines.append(f"\n<b>{esc(current_group)}</b>")
            signature = f"{deps.prefix}{command.name} {command.usage}".strip()
            lines.append(f"{code(signature)} — {esc(command.summary)}")
        return CommandResult(html="\n".join(lines))

    async def ping(context: CommandContext) -> CommandResult:
        rtt = await deps.telegram.ping()
        delivery = (context.received_at - context.sent_at).total_seconds()
        delivery_text = "< 1 с" if delivery < 1 else f"≈{delivery:.0f} с"
        connected = "✅" if deps.telegram.is_connected() else "❌"
        return CommandResult(
            html=(
                f"🏓 <b>Pong</b>\n"
                f"Telegram API: <b>{rtt * 1000:.0f} мс</b>\n"
                f"Доставка команди: {delivery_text}\n"
                f"З'єднання: {connected}"
            )
        )

    async def uptime(_: CommandContext) -> CommandResult:
        now = runtime.clock.now()
        boot = host_info().boot_time
        return CommandResult(
            html=(
                f"⏱ Аптайм: <b>{human_duration(now - runtime.started_at)}</b>\n"
                f"Запущено: {game_time(runtime.started_at)} (UTC+3)\n"
                f"Сервер працює: {human_duration(now - boot)}"
            )
        )

    async def version(_: CommandContext) -> CommandResult:
        return CommandResult(
            html=(
                f"🐸 Toad Userbot <b>{esc(runtime.build.version)}</b>\n"
                f"Коміт: {code(runtime.build.git_commit)}"
            )
        )

    async def restart(_: CommandContext) -> CommandResult:
        return CommandResult(
            html="♻️ Перезапускаюся…",
            after_reply=lambda: runtime.shutdown.request(EXIT_RESTART),
        )

    return [
        Command("help", GROUP, "список команд", help_command, aliases=("h",)),
        Command("ping", GROUP, "затримка до Telegram", ping),
        Command("uptime", GROUP, "час роботи", uptime),
        Command("version", GROUP, "версія і коміт", version, aliases=("v",)),
        Command("restart", GROUP, "перезапустити процес", restart),
    ]
