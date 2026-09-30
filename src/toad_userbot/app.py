"""Composition root: builds every component, runs until shutdown, cleans up."""

from __future__ import annotations

import asyncio
import contextlib
import signal
from typing import Final, Protocol

import structlog

from toad_userbot import __version__
from toad_userbot.config import AppConfig, Paths, Settings
from toad_userbot.control.commands import CommandDeps, build_commands
from toad_userbot.control.dispatcher import ControlDispatcher
from toad_userbot.control.ports import KeyValueStore, TelegramInfo
from toad_userbot.control.registry import CommandRegistry
from toad_userbot.domain.time import SystemClock
from toad_userbot.recorder.policy import RecordingPolicy
from toad_userbot.recorder.service import Recorder
from toad_userbot.runtime import (
    TARGET_CHAT_META_KEY,
    BotIdentity,
    BuildInfo,
    ChatSource,
    Runtime,
    Shutdown,
    TargetChat,
)
from toad_userbot.storage.db import Database
from toad_userbot.storage.repositories import MessageRepository, MetaRepository
from toad_userbot.system.heartbeat import Heartbeat
from toad_userbot.telegram.client import NotAuthorizedError, TelegramConnection, build_client
from toad_userbot.telegram.control_bridge import ControlBridge
from toad_userbot.telegram.info import TelethonInfo
from toad_userbot.telegram.router import TelegramRouter

log = structlog.get_logger(__name__)

EXIT_NOT_AUTHORIZED: Final = 2
EXIT_DISCONNECTED: Final = 1


class UsernameResolver(Protocol):
    async def resolve_user_id(self, username: str) -> int: ...


class DisconnectWatcher(Protocol):
    async def wait_disconnected(self) -> None: ...


async def run(settings: Settings, config: AppConfig) -> int:
    paths = settings.paths
    paths.ensure()
    clock = SystemClock()
    started_at = clock.now()
    shutdown = Shutdown()
    log.info("app.starting", version=__version__, commit=settings.git_commit)

    db = Database(paths.database)
    connection = TelegramConnection(
        build_client(
            session_path=paths.session,
            api_id=settings.tg_api_id,
            api_hash=settings.tg_api_hash.get_secret_value(),
            app_version=__version__,
        )
    )
    heartbeat: asyncio.Task[None] | None = None
    try:
        await db.connect()
        _restrict_permissions(paths)
        try:
            account = await connection.open()
        except NotAuthorizedError:
            log.error("app.not_authorized", hint="run `toad-userbot login` first")
            shutdown.request(EXIT_NOT_AUTHORIZED)
            return shutdown.exit_code

        client = connection.client
        info = TelethonInfo(client)
        meta = MetaRepository(db)
        messages = MessageRepository(db)

        bot = await _resolve_bot(connection, meta, config.bot_username)
        target = await _resolve_target(info, meta, config.chat_id)
        runtime = Runtime(
            started_at=started_at,
            build=BuildInfo(__version__, settings.git_commit),
            paths=paths,
            clock=clock,
            shutdown=shutdown,
            target=target,
            bot=bot,
            config_chat_id=config.chat_id,
        )

        recorder = Recorder(
            store=messages,
            policy=RecordingPolicy(
                bot_id=bot.id,
                bot_username=bot.username,
                command_words=config.recorder.command_words,
            ),
            clock=clock,
            enabled=config.recorder.enabled,
        )

        registry = CommandRegistry()
        prefix = config.control.prefix
        registry.register_all(
            build_commands(
                CommandDeps(
                    runtime=runtime,
                    telegram=info,
                    recorder=recorder,
                    messages=messages,
                    meta=meta,
                    registry=registry,
                    prefix=prefix,
                )
            )
        )
        bridge = ControlBridge(
            client=client,
            dispatcher=ControlDispatcher(registry, prefix),
            clock=clock,
            started_at=started_at,
        )
        TelegramRouter(
            client=client,
            recorder=recorder,
            control=bridge,
            target=target,
            self_id=account.id,
            bot_id=bot.id,
            clock=clock,
        ).install()

        heartbeat = asyncio.create_task(Heartbeat(paths.heartbeat, clock).run())
        _install_signal_handlers(shutdown)
        log.info(
            "app.started",
            account_id=account.id,
            chat_id=target.id,
            chat_source=target.source.value,
            bot_id=bot.id,
            recording=recorder.enabled,
        )
        if target.id is None:
            log.warning("app.chat_not_configured", hint=f"use {prefix}chats and {prefix}chat set")

        await _wait_for_stop(connection, shutdown)
    finally:
        if heartbeat is not None:
            heartbeat.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await heartbeat
        await connection.close()
        await db.close()
        log.info("app.stopped", exit_code=shutdown.exit_code)
    return shutdown.exit_code


async def _resolve_bot(
    connection: UsernameResolver, meta: KeyValueStore, username: str
) -> BotIdentity:
    """Resolve the bot's user id once and cache it: username lookups are rate limited."""
    key = f"bot_id:{username}"
    cached = await meta.get(key)
    if cached is not None:
        return BotIdentity(username=username, id=int(cached))
    bot_id = await connection.resolve_user_id(username)
    await meta.set(key, str(bot_id))
    return BotIdentity(username=username, id=bot_id)


async def _resolve_target(
    info: TelegramInfo, meta: KeyValueStore, config_chat_id: int | None
) -> TargetChat:
    override = await meta.get(TARGET_CHAT_META_KEY)
    chat_id, source = (
        (int(override), ChatSource.OVERRIDE) if override else (config_chat_id, ChatSource.CONFIG)
    )
    target = TargetChat()
    if chat_id is None:
        return target

    found = await info.find_group(chat_id)
    if found is None:
        log.warning("app.chat_not_found", chat_id=chat_id, source=source.value)
    target.update(chat_id, found.title if found else None, source)
    return target


async def _wait_for_stop(connection: DisconnectWatcher, shutdown: Shutdown) -> None:
    stop = asyncio.create_task(shutdown.wait())
    disconnected = asyncio.create_task(connection.wait_disconnected())
    done, pending = await asyncio.wait({stop, disconnected}, return_when=asyncio.FIRST_COMPLETED)
    for task in pending:
        task.cancel()
    if disconnected in done and not shutdown.requested:
        log.error("telegram.disconnected")
        shutdown.request(EXIT_DISCONNECTED)


def _restrict_permissions(paths: Paths) -> None:
    """The session grants full account access; keep it and the database owner-only."""
    for path in (paths.session, paths.database):
        with contextlib.suppress(FileNotFoundError):
            path.chmod(0o600)


def _install_signal_handlers(shutdown: Shutdown) -> None:
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        with contextlib.suppress(NotImplementedError):  # not supported on Windows
            loop.add_signal_handler(sig, shutdown.request, 0)
