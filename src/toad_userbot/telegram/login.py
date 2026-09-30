"""Interactive login that creates the session file. Run once, by the account owner.

Two methods:

* **QR code** (default) — the owner scans a QR code from the Telegram app on the phone
  (Settings → Devices → Link Desktop Device). No login code is involved, so it works even when
  Telegram does not deliver codes to a new third-party client on a data-center IP.
* **Login code** — unlike ``TelegramClient.start()``, tells where Telegram delivered the code
  (app, SMS, e-mail, call, Fragment), lets the owner request it another way, and explains the
  cases in which Telegram will not send a code at all.
"""

from __future__ import annotations

import getpass
import sys
from collections.abc import Callable, Sequence
from typing import Any, Final

import qrcode
from telethon import TelegramClient, errors
from telethon.tl import functions, types

from toad_userbot import __version__
from toad_userbot.config import Settings
from toad_userbot.control.ports import AccountInfo
from toad_userbot.telegram.client import account_info, build_client

MAX_CODE_ATTEMPTS: Final = 5
MAX_PASSWORD_ATTEMPTS: Final = 3
# A login token lives about 30 seconds; this gives the owner roughly four minutes.
MAX_QR_ROUNDS: Final = 8

_QR_HELP: Final = (
    "📱 Відкрий Telegram на телефоні → Налаштування → Пристрої → «Підключити пристрій»\n"
    "   (Link Desktop Device) і відскануй QR-код нижче. Telegram попросить підтвердити\n"
    "   вхід нового пристрою «Toad Userbot». QR оновлюється сам кожні ~30 секунд."
)

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
_API_ID_INVALID: Final = (
    "Telegram не прийняв api_id / api_hash. Перевір значення з https://my.telegram.org "
    "у /etc/toad-userbot/env"
)
_DO_NOT_SHARE: Final = (
    "   ⚠️ Вводь код лише тут. Не пересилай його і не вставляй у жоден чат, "
    "навіть у «Збережене»: Telegram анулює такий код."
)

Ask = Callable[[str], str]
Say = Callable[[str], None]
Render = Callable[[str], str]

# ANSI colours: dark modules black, light modules bright white — correct polarity for scanning
# in both dark and light terminal themes.
_FG = {True: "30", False: "97"}
_BG = {True: "40", False: "107"}
_RESET: Final = "\033[0m"


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


def render_qr(data: str) -> str:
    """Render ``data`` as a QR code with half-block characters: one text line per two rows."""
    qr = qrcode.QRCode(border=4, error_correction=qrcode.constants.ERROR_CORRECT_L)
    qr.add_data(data)
    qr.make(fit=True)
    return render_matrix(qr.get_matrix())


def render_matrix(matrix: Sequence[Sequence[bool]]) -> str:
    lines: list[str] = []
    for top_index in range(0, len(matrix), 2):
        top = matrix[top_index]
        bottom = matrix[top_index + 1] if top_index + 1 < len(matrix) else [False] * len(top)
        cells = "".join(
            f"\033[{_FG[bool(upper)]};{_BG[bool(lower)]}m▀"
            for upper, lower in zip(top, bottom, strict=True)
        )
        lines.append(cells + _RESET)
    return "\n".join(lines)


async def login(settings: Settings, *, use_code: bool = False) -> int:
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
        elif use_code:
            me = await sign_in_interactively(client)
        else:
            me = await sign_in_with_qr(client)
    except LoginAbortedError as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 1
    finally:
        await client.disconnect()

    paths.session.chmod(0o600)
    print(f"✅ Увійшли як {me.name} (id {me.id}).")
    print(f"Сесію збережено: {paths.session}")
    return 0


async def sign_in_with_qr(
    client: TelegramClient,
    *,
    ask_secret: Ask = getpass.getpass,
    say: Say = print,
    render: Render = render_qr,
    rounds: int = MAX_QR_ROUNDS,
) -> AccountInfo:
    try:
        qr = await client.qr_login()
    except errors.FloodWaitError as exc:
        msg = f"Telegram просить зачекати {exc.seconds} с перед новою спробою входу"
        raise LoginAbortedError(msg) from exc
    except errors.ApiIdInvalidError as exc:
        raise LoginAbortedError(_API_ID_INVALID) from exc

    say(_QR_HELP)
    for round_number in range(rounds):
        if round_number:
            await qr.recreate()
            say("⏳ QR прострочився, ось новий:")
        say(render(qr.url))
        try:
            user = await qr.wait()
        except TimeoutError:
            continue
        except errors.SessionPasswordNeededError:
            return await _sign_in_with_password(client, ask_secret, say)
        return account_info(user)

    msg = "QR-код так і не відскановано. Запусти вхід ще раз або спробуй вхід за кодом (--code)"
    raise LoginAbortedError(msg)


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
    except errors.ApiIdInvalidError as exc:
        raise LoginAbortedError(_API_ID_INVALID) from exc
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
