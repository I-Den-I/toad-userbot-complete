"""Recorder and chat commands: status, export, chat, chats."""

from __future__ import annotations

import json
from datetime import timedelta
from typing import TYPE_CHECKING, Final

from toad_userbot.control.format import ago, code, esc, human_bytes, human_duration
from toad_userbot.control.registry import (
    Attachment,
    Command,
    CommandContext,
    CommandResult,
    UsageError,
)
from toad_userbot.domain.time import to_game_time
from toad_userbot.runtime import TARGET_CHAT_META_KEY, ChatSource
from toad_userbot.system.metrics import path_size

if TYPE_CHECKING:
    from toad_userbot.control.commands import CommandDeps

GROUP = "Запис і чат"

DEFAULT_EXPORT_HOURS: Final = 24
MAX_EXPORT_HOURS: Final = 24 * 30
CHATS_LIMIT: Final = 30

_SOURCE_LABELS: Final = {
    ChatSource.CONFIG: "з config.yaml",
    ChatSource.OVERRIDE: "задано командою .chat set",
    ChatSource.NONE: "",
}


def build(deps: CommandDeps) -> list[Command]:
    runtime = deps.runtime
    target = runtime.target

    def describe_target() -> str:
        if target.id is None:
            return (
                f"⚠️ не налаштовано — знайди id через {code(deps.prefix + 'chats')} "
                f"і задай {code(deps.prefix + 'chat set <id>')}"
            )
        title = esc(target.title or "?")
        return f"{title} ({code(target.id)}, {_SOURCE_LABELS[target.source]})"

    async def status(_: CommandContext) -> CommandResult:
        now = runtime.clock.now()
        account = await deps.telegram.account()
        stats = await deps.messages.stats(now)
        counters = deps.recorder.counters
        username = f"@{account.username}, " if account.username else ""
        last_bot = ago(stats.last_bot_message_at, now) if stats.last_bot_message_at else "—"
        connected = "✅ підключено" if deps.telegram.is_connected() else "❌ немає з'єднання"
        recording = "увімкнено" if deps.recorder.enabled else "вимкнено"
        lines = [
            f"🐸 <b>Toad Userbot</b> {esc(runtime.build.version)} "
            f"({code(runtime.build.git_commit[:7])})",
            f"⏱ Аптайм: {human_duration(now - runtime.started_at)}",
            f"📡 Telegram: {connected}",
            f"👤 Акаунт: {esc(account.name)} ({esc(username)}{code(account.id)})",
            f"💬 Чат: {describe_target()}",
            f"🤖 Бот: @{esc(runtime.bot.username)} ({code(runtime.bot.id)})",
            f"📼 Запис: {recording}",
            f"   за сесію: {counters.recorded} (від бота {counters.recorded_from_bot}), "
            f"видалено ботом: {counters.deletions}",
            f"   у БД: {stats.total} (від бота {stats.from_bot}), за 24 год: {stats.last_24h}",
            f"   останнє від бота: {last_bot}",
            f"🗄 БД: {human_bytes(path_size(runtime.paths.database))}",
        ]
        return CommandResult(html="\n".join(lines))

    async def export(context: CommandContext) -> CommandResult:
        hours = _parse_hours(context.args)
        now = runtime.clock.now()
        rows = await deps.messages.export_since(now - timedelta(hours=hours))
        if not rows:
            return CommandResult(html=f"📭 Немає записів за останні {hours} год.")
        content = "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n"
        stamp = to_game_time(now).strftime("%Y%m%d-%H%M")
        caption = f"📦 {len(rows)} повідомлень за {hours} год"
        return CommandResult(
            html=f"{caption} — у файлі нижче.",
            attachment=Attachment(f"toadbot-{stamp}-{hours}h.jsonl", content.encode(), caption),
        )

    async def chat(context: CommandContext) -> CommandResult:
        match context.args:
            case ():
                return CommandResult(html=f"💬 Чат: {describe_target()}")
            case ("set", raw_id):
                chat_id = _parse_chat_id(raw_id)
                found = await deps.telegram.find_group(chat_id)
                if found is None:
                    msg = f"групу {chat_id} не знайдено серед твоїх діалогів"
                    raise UsageError(msg)
                await deps.meta.set(TARGET_CHAT_META_KEY, str(found.id))
                target.update(found.id, found.title, ChatSource.OVERRIDE)
                return CommandResult(
                    html=f"✅ Тепер працюю в чаті: {describe_target()}. Збережено в БД."
                )
            case ("reset",):
                await deps.meta.delete(TARGET_CHAT_META_KEY)
                config_id = runtime.config_chat_id
                found = await deps.telegram.find_group(config_id) if config_id else None
                target.update(config_id, found.title if found else None, ChatSource.CONFIG)
                return CommandResult(html=f"↩️ Повернуто чат із конфігу: {describe_target()}")
            case _:
                msg = "очікується: без аргументів, «set <id>» або «reset»"
                raise UsageError(msg)

    async def chats(context: CommandContext) -> CommandResult:
        query = " ".join(context.args) or None
        groups = await deps.telegram.groups(query, CHATS_LIMIT)
        if not groups:
            return CommandResult(html="🔍 Нічого не знайдено.")
        lines = [f"🔍 <b>Групи</b> (до {CHATS_LIMIT}):"]
        lines += [f"{code(group.id)} — {esc(group.title)}" for group in groups]
        lines.append(f"\nЗадати робочий чат: {code(deps.prefix + 'chat set <id>')}")
        return CommandResult(html="\n".join(lines))

    return [
        Command("status", GROUP, "стан юзербота і запису", status, aliases=("s",)),
        Command(
            "export",
            GROUP,
            f"вивантажити записані повідомлення в JSONL (типово {DEFAULT_EXPORT_HOURS} год)",
            export,
            usage="[годин]",
        ),
        Command("chat", GROUP, "показати або змінити робочий чат", chat, usage="[set <id>|reset]"),
        Command("chats", GROUP, "знайти групи та їхні id", chats, usage="[фільтр]"),
    ]


def _parse_hours(args: tuple[str, ...]) -> int:
    if not args:
        return DEFAULT_EXPORT_HOURS
    if len(args) != 1 or not args[0].isdigit():
        msg = "кількість годин має бути цілим числом"
        raise UsageError(msg)
    hours = int(args[0])
    if not 1 <= hours <= MAX_EXPORT_HOURS:
        msg = f"кількість годин має бути від 1 до {MAX_EXPORT_HOURS}"
        raise UsageError(msg)
    return hours


def _parse_chat_id(raw: str) -> int:
    try:
        return int(raw)
    except ValueError:
        msg = f"«{raw}» не схоже на id чату"
        raise UsageError(msg) from None
