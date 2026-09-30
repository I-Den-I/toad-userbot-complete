"""Interactive login that creates the session file. Run once, by the account owner."""

from __future__ import annotations

import getpass

from toad_userbot import __version__
from toad_userbot.config import Settings
from toad_userbot.telegram.client import account_info, build_client


async def login(settings: Settings) -> int:
    paths = settings.paths
    paths.ensure()
    client = build_client(
        session_path=paths.session,
        api_id=settings.tg_api_id,
        api_hash=settings.tg_api_hash.get_secret_value(),
        app_version=__version__,
    )
    try:
        await client.start(
            phone=lambda: input("Номер телефону у міжнародному форматі (+380…): "),
            code_callback=lambda: input("Код підтвердження з Telegram: "),
            password=lambda: getpass.getpass("Пароль двофакторної автентифікації: "),
        )
        me = account_info(await client.get_me())
    finally:
        await client.disconnect()

    paths.session.chmod(0o600)
    print(f"✅ Увійшли як {me.name} (id {me.id}).")
    print(f"Сесію збережено: {paths.session}")
    print("Далі: toad-userbot run")
    return 0
