"""Interactive login that creates the session file. Run once, by the account owner.

Unlike ``TelegramClient.start()``, this flow tells the owner where Telegram delivered the
code (app, SMS, e-mail, call, Fragment), lets them request it another way, and explains the
cases in which Telegram will not send a code at all.
"""

from __future__ import annotations

import getpass
import sys
from collections.abc import Callable
from typing import Any, Final

from telethon import TelegramClient, errors
from telethon.tl import functions, types

from toad_userbot import __version__
from toad_userbot.config import Settings
from toad_userbot.control.ports import AccountInfo
from toad_userbot.telegram.client import account_info, build_client

MAX_CODE_ATTEMPTS: Final = 5
MAX_PASSWORD_ATTEMPTS: Final = 3

_DELIVERY: Final = {
    "SentCodeTypeApp": (
        "у застосунок Telegram — службовий чат «Telegram» із синьою галочкою "
        "на будь-якому пристрої, де ти залогінений"
    ),
    "SentCodeTypeSms": "SMS",
    "SentCodeTypeSmsWord": "SMS зі словом — введи це слово",
    "SentCodeTypeSmsPhrase": "SMS з фразою — введи цю фразу",
    "SentCodeTypeFirebaseSms": "SMS",
    "SentCodeTypeCall": "голосовим дзвінком",
    "SentCodeTypeFlashCall": "дзвінком-скиданням — код це останні цифри номера, що дзвонив",
    "SentCodeTypeMissedCall": "пропущеним дзвінком — код це останні цифри номера, що дзвонив",
    "SentCodeTypeFragmentSms": "через Fragment (анонімний номер)",
    "SentCodeTypeEmailCode": "на пошту для входу",
}
_NEXT: Final = {
    "CodeTypeSms": "SMS",
    "CodeTypeCall": "голосовий дзвінок",
    "CodeTypeFlashCall": "дзвінок-скидання",
    "CodeTypeMissedCall": "пропущений дзвінок",
    "CodeTypeFragmentSms": "код через Fragment",
}
_DO_NOT_SHARE: Final = (
    "   ⚠️ Вводь код лише тут. Не пересилай його і не вставляй у жоден чат, "
    "навіть у «Збережене»: Telegram анулює такий код."
)

Ask = Callable[[str], str]
Say = Callable[[str], None]


class LoginAbortedError(Exception):
    """Login cannot continue; the message explains why to the owner."""


def describe_delivery(sent: types.auth.SentCode) -> str:
    kind = type(sent.type).__name__
    text = _DELIVERY.get(kind, kind)
    if isinstance(sent.type, types.auth.SentCodeTypeEmailCode):
        text += f" ({sent.type.email_pattern})"
    elif isinstance(sent.type, types.auth.SentCodeTypeFragmentSms):
        text += f": {sent.type.url}"
    length = getattr(sent.type, "length", None)
    if length:
        text += f", {length} символів"
    return text


def describe_next(sent: types.auth.SentCode) -> str | None:
    if sent.next_type is None:
        return None
    kind = type(sent.next_type).__name__
    text = _NEXT.get(kind, kind)
    if sent.timeout:
        text += f" (не раніше ніж через {sent.timeout} с)"
    return text


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
        await client.connect()
        if await client.is_user_authorized():
            me = account_info(await client.get_me())
            print(f"ℹ️ Сесія вже активна: {me.name} (id {me.id}).")
        else:
            me = await sign_in_interactively(client)
    except LoginAbortedError as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 1
    finally:
        await client.disconnect()

    paths.session.chmod(0o600)
    print(f"✅ Увійшли як {me.name} (id {me.id}).")
    print(f"Сесію збережено: {paths.session}")
    return 0


async def sign_in_interactively(
    client: TelegramClient,
    *,
    ask: Ask = input,
    ask_secret: Ask = getpass.getpass,
    say: Say = print,
) -> AccountInfo:
    phone = _ask(ask, "Номер телефону у міжнародному форматі (+380…): ")
    sent = await _request_code(client, phone, None, say)

    for _ in range(MAX_CODE_ATTEMPTS):
        code = _ask(ask, "Код (порожній Enter — надіслати іншим способом): ")
        if not code:
            sent = await _request_code(client, phone, sent, say)
            continue
        try:
            user = await client.sign_in(phone, code, phone_code_hash=sent.phone_code_hash)
        except errors.PhoneCodeInvalidError:
            say("Невірний код, спробуй ще раз.")
        except errors.PhoneCodeExpiredError:
            say("Код прострочений, надсилаю новий.")
            sent = await _request_code(client, phone, None, say)
        except errors.SessionPasswordNeededError:
            return await _sign_in_with_password(client, ask_secret, say)
        else:
            return account_info(user)

    msg = "забагато спроб введення коду. Зачекай кілька хвилин і запусти вхід знову"
    raise LoginAbortedError(msg)


async def _request_code(
    client: TelegramClient, phone: str, previous: types.auth.SentCode | None, say: Say
) -> types.auth.SentCode:
    """Send a code, or ask Telegram for the next delivery method if one was already sent.

    The raw API is used instead of ``send_code_request``: Telethon's helper crashes on
    ``SentCodePaymentRequired`` and hides where the code went.
    """
    try:
        if previous is None:
            request: Any = functions.auth.SendCodeRequest(
                phone, client.api_id, client.api_hash, types.CodeSettings()
            )
        else:
            request = functions.auth.ResendCodeRequest(phone, previous.phone_code_hash)
        sent = await client(request)
    except errors.PhoneCodeExpiredError:
        if previous is None:
            raise
        return await _request_code(client, phone, None, say)
    except errors.FloodWaitError as exc:
        msg = f"Telegram просить зачекати {exc.seconds} с перед новим запитом коду"
        raise LoginAbortedError(msg) from exc
    except errors.PhoneNumberInvalidError as exc:
        msg = "номер телефону не розпізнано: введи його разом з кодом країни, напр. +380…"
        raise LoginAbortedError(msg) from exc
    except errors.PhoneNumberBannedError as exc:
        msg = "цей номер заблоковано в Telegram"
        raise LoginAbortedError(msg) from exc
    except errors.SendCodeUnavailableError as exc:
        msg = "інших способів надіслати код Telegram не має. Спробуй пізніше"
        raise LoginAbortedError(msg) from exc

    _raise_if_undeliverable(sent)
    say(f"📨 Код надіслано {describe_delivery(sent)}.")
    alternative = describe_next(sent)
    if alternative:
        say(f"   Не прийшов? Натисни Enter замість коду, і Telegram надішле: {alternative}.")
    say(_DO_NOT_SHARE)
    return sent


def _raise_if_undeliverable(sent: Any) -> None:
    if isinstance(sent, types.auth.SentCodePaymentRequired):
        msg = (
            "Telegram вимагає оплату за SMS для цього входу. Відкрий застосунок Telegram "
            "на телефоні, переконайся, що сесія активна, і спробуй вхід пізніше"
        )
        raise LoginAbortedError(msg)
    if not isinstance(sent, types.auth.SentCode):
        msg = f"неочікувана відповідь Telegram ({type(sent).__name__}). Спробуй вхід ще раз"
        raise LoginAbortedError(msg)
    if isinstance(sent.type, types.auth.SentCodeTypeSetUpEmailRequired):
        msg = (
            "Telegram вимагає спершу налаштувати пошту для входу. Зроби це в офіційному "
            "застосунку: Налаштування → Конфіденційність → Пошта для входу, потім повтори"
        )
        raise LoginAbortedError(msg)


async def _sign_in_with_password(client: TelegramClient, ask_secret: Ask, say: Say) -> AccountInfo:
    for _ in range(MAX_PASSWORD_ATTEMPTS):
        password = ask_secret("Пароль двофакторної автентифікації: ")
        try:
            user = await client.sign_in(password=password)
        except errors.PasswordHashInvalidError:
            say("Невірний пароль, спробуй ще раз.")
        else:
            return account_info(user)
    msg = "забагато невдалих спроб пароля"
    raise LoginAbortedError(msg)


def _ask(ask: Ask, prompt: str) -> str:
    try:
        return ask(prompt).strip()
    except (EOFError, KeyboardInterrupt) as exc:
        msg = "вхід скасовано"
        raise LoginAbortedError(msg) from exc
