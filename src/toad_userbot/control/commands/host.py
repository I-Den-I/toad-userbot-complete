"""Server commands: cpu, mem, disk, sys, logs."""

from __future__ import annotations

import asyncio
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as package_version
from typing import TYPE_CHECKING, Final

from toad_userbot.control.format import esc, game_time, human_bytes, percent, pre
from toad_userbot.control.registry import (
    Attachment,
    Command,
    CommandContext,
    CommandResult,
    UsageError,
)
from toad_userbot.system.logtail import LEVELS, filter_by_level, tail_lines
from toad_userbot.system.metrics import (
    host_info,
    path_size,
    sample_cpu,
    sample_disk,
    sample_memory,
)

if TYPE_CHECKING:
    from pathlib import Path

    from toad_userbot.control.commands import CommandDeps

GROUP = "Сервер"

DEFAULT_LOG_LINES: Final = 30
MAX_LOG_LINES: Final = 500
# Level filtering scans this many lines per requested line before giving up.
LEVEL_SCAN_FACTOR: Final = 20
# Longer output goes into a file: a message is limited to 4096 characters.
INLINE_LIMIT: Final = 3500


def build(deps: CommandDeps) -> list[Command]:
    paths = deps.runtime.paths

    async def cpu(_: CommandContext) -> CommandResult:
        snapshot = await asyncio.to_thread(sample_cpu)
        lines = [
            "🧠 <b>CPU</b>",
            f"Процес: {percent(snapshot.process_percent)}",
            f"Система: {percent(snapshot.system_percent)} ({snapshot.cores} ядер)",
        ]
        if snapshot.load_average is not None:
            load = " / ".join(f"{value:.2f}" for value in snapshot.load_average)
            lines.append(f"Load average: {load}")
        return CommandResult(html="\n".join(lines))

    async def mem(_: CommandContext) -> CommandResult:
        snapshot = await asyncio.to_thread(sample_memory)
        lines = ["💾 <b>Пам'ять</b>", f"Процес (RSS): {human_bytes(snapshot.process_rss)}"]
        if snapshot.container_current is not None:
            limit = (
                human_bytes(snapshot.container_limit)
                if snapshot.container_limit is not None
                else "без ліміту"
            )
            lines.append(f"Контейнер: {human_bytes(snapshot.container_current)} з {limit}")
        lines += [
            (
                f"Система: {human_bytes(snapshot.system_used)} / "
                f"{human_bytes(snapshot.system_total)} ({percent(snapshot.system_percent)}), "
                f"доступно {human_bytes(snapshot.system_available)}"
            ),
            f"Swap: {human_bytes(snapshot.swap_used)} / {human_bytes(snapshot.swap_total)}",
        ]
        return CommandResult(html="\n".join(lines))

    async def disk(_: CommandContext) -> CommandResult:
        snapshot = await asyncio.to_thread(sample_disk, paths.data_dir)
        database = sum(
            path_size(path)
            for path in (
                paths.database,
                paths.database.with_name(paths.database.name + "-wal"),
                paths.database.with_name(paths.database.name + "-shm"),
            )
        )
        return CommandResult(
            html=(
                "🗄 <b>Диск</b> (том з даними)\n"
                f"Зайнято: {human_bytes(snapshot.used)} / {human_bytes(snapshot.total)} "
                f"({percent(snapshot.percent)}), вільно {human_bytes(snapshot.free)}\n"
                f"БД: {human_bytes(database)} · "
                f"логи: {human_bytes(path_size(paths.logs_dir))} · "
                f"сесія: {human_bytes(path_size(paths.session))}"
            )
        )

    async def sys_info(_: CommandContext) -> CommandResult:
        info = host_info()
        container = " (Docker)" if info.in_container else ""
        return CommandResult(
            html=(
                "🖥 <b>Система</b>\n"
                f"Хост: {esc(info.hostname)}{container}\n"
                f"ОС: {esc(info.platform)}\n"
                f"Python: {esc(info.python)} · Telethon: {esc(_package_version('telethon'))}\n"
                f"PID: {info.pid}\n"
                f"Сервер запущено: {game_time(info.boot_time)} (UTC+3)"
            )
        )

    async def logs(context: CommandContext) -> CommandResult:
        count, level = _parse_log_args(context.args)
        text, shown = await asyncio.to_thread(_read_logs, paths.log_file, count, level)
        title = f"📜 Останні {shown} рядків логу" + (f" (рівень ≥ {level})" if level else "")
        if len(text) > INLINE_LIMIT:
            return CommandResult(
                html=f"{title} — у файлі нижче.",
                attachment=Attachment("userbot-log.txt", text.encode("utf-8"), f"📜 {title}"),
            )
        return CommandResult(html=f"{title}\n{pre(text or '(порожньо)')}")

    return [
        Command("cpu", GROUP, "навантаження CPU", cpu),
        Command("mem", GROUP, "пам'ять процесу, контейнера і сервера", mem),
        Command("disk", GROUP, "місце на диску, розмір БД і логів", disk),
        Command("sys", GROUP, "хост, ОС, версії", sys_info),
        Command(
            "logs",
            GROUP,
            f"останні рядки логу (типово {DEFAULT_LOG_LINES}), опційно мінімальний рівень",
            logs,
            usage=f"[N] [{'|'.join(LEVELS[:4])}]",
            aliases=("log",),
        ),
    ]


def _parse_log_args(args: tuple[str, ...]) -> tuple[int, str | None]:
    count = DEFAULT_LOG_LINES
    level: str | None = None
    for arg in args:
        lowered = arg.casefold()
        if lowered.isdigit():
            count = int(lowered)
        elif lowered in LEVELS:
            level = lowered
        else:
            msg = f"незрозумілий аргумент «{arg}»"
            raise UsageError(msg)
    if not 1 <= count <= MAX_LOG_LINES:
        msg = f"кількість рядків має бути від 1 до {MAX_LOG_LINES}"
        raise UsageError(msg)
    return count, level


def _read_logs(path: Path, count: int, level: str | None) -> tuple[str, int]:
    if level is None:
        lines = tail_lines(path, count)
    else:
        lines = filter_by_level(tail_lines(path, count * LEVEL_SCAN_FACTOR), level)[-count:]
    return "\n".join(lines), len(lines)


def _package_version(name: str) -> str:
    try:
        return package_version(name)
    except PackageNotFoundError:
        return "?"
