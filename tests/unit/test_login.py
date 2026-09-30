"""Interactive login flow with real Telethon TL objects and a scripted fake client."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

import pytest
from telethon import errors
from telethon.tl import functions, types

from toad_userbot.telegram.login import (
    LoginAbortedError,
    describe_delivery,
    describe_next,
    sign_in_interactively,
)

USER = SimpleNamespace(id=42, first_name="Скала", last_name=None, username="skala")


def _sent(
    kind: Any, *, hash_: str = "h1", next_type: Any = None, timeout: int | None = None
) -> Any:
    return types.auth.SentCode(
        type=kind, phone_code_hash=hash_, next_type=next_type, timeout=timeout
    )


@dataclass
class ScriptedClient:
    """Answers API requests and sign-in attempts from pre-recorded scripts."""

    code_responses: list[Any]
    sign_in_results: list[Any]
    api_id: int = 12345
    api_hash: str = "0" * 32
    requests: list[Any] = field(default_factory=list)
    sign_ins: list[dict[str, Any]] = field(default_factory=list)

    async def __call__(self, request: Any) -> Any:
        self.requests.append(request)
        return _next(self.code_responses)

    async def sign_in(
        self, phone: str | None = None, code: str | None = None, **kwargs: Any
    ) -> Any:
        self.sign_ins.append({"phone": phone, "code": code, **kwargs})
        return _next(self.sign_in_results)


def _next(script: list[Any]) -> Any:
    item = script.pop(0)
    if isinstance(item, BaseException):
        raise item
    return item


def _answers(*values: str) -> Iterator[str]:
    return iter(values)


def test_describe_app_code_with_sms_fallback() -> None:
    sent = _sent(
        types.auth.SentCodeTypeApp(length=5), next_type=types.auth.CodeTypeSms(), timeout=60
    )

    assert "службовий чат «Telegram»" in describe_delivery(sent)
    assert "5 символів" in describe_delivery(sent)
    assert describe_next(sent) == "SMS (не раніше ніж через 60 с)"


def test_describe_email_and_fragment() -> None:
    email = _sent(types.auth.SentCodeTypeEmailCode(email_pattern="n***@gmail.com", length=6))
    fragment = _sent(types.auth.SentCodeTypeFragmentSms(url="https://fragment.com/x", length=5))

    assert "n***@gmail.com" in describe_delivery(email)
    assert "https://fragment.com/x" in describe_delivery(fragment)
    assert describe_next(email) is None


async def test_resend_then_wrong_code_then_two_factor() -> None:
    client = ScriptedClient(
        code_responses=[
            _sent(
                types.auth.SentCodeTypeApp(length=5), hash_="h1", next_type=types.auth.CodeTypeSms()
            ),
            _sent(types.auth.SentCodeTypeSms(length=5), hash_="h2"),
        ],
        sign_in_results=[
            errors.PhoneCodeInvalidError(request=None),
            errors.SessionPasswordNeededError(request=None),
            errors.PasswordHashInvalidError(request=None),
            USER,
        ],
    )
    answers = _answers("+380000000000", "", "11111", "22222")
    secrets = _answers("wrong", "right")
    said: list[str] = []

    account = await sign_in_interactively(
        client,
        ask=lambda _: next(answers),
        ask_secret=lambda _: next(secrets),
        say=said.append,
    )

    assert (account.id, account.username) == (42, "skala")
    assert isinstance(client.requests[0], functions.auth.SendCodeRequest)
    assert isinstance(client.requests[1], functions.auth.ResendCodeRequest)
    assert client.requests[1].phone_code_hash == "h1"
    assert [attempt.get("phone_code_hash") for attempt in client.sign_ins[:2]] == ["h2", "h2"]
    assert client.sign_ins[-1] == {"phone": None, "code": None, "password": "right"}
    text = "\n".join(said)
    assert "службовий чат «Telegram»" in text
    assert "Натисни Enter" in text
    assert "Невірний код" in text
    assert "Невірний пароль" in text
    assert "не вставляй у жоден чат" in text


async def test_expired_resend_hash_starts_over() -> None:
    client = ScriptedClient(
        code_responses=[
            _sent(types.auth.SentCodeTypeApp(length=5), hash_="h1"),
            errors.PhoneCodeExpiredError(request=None),
            _sent(types.auth.SentCodeTypeApp(length=5), hash_="h3"),
        ],
        sign_in_results=[USER],
    )
    answers = _answers("+380000000000", "", "12345")

    await sign_in_interactively(client, ask=lambda _: next(answers), say=lambda _: None)

    assert [type(request).__name__ for request in client.requests] == [
        "SendCodeRequest",
        "ResendCodeRequest",
        "SendCodeRequest",
    ]
    assert client.sign_ins[0]["phone_code_hash"] == "h3"


@pytest.mark.parametrize(
    ("response", "message"),
    [
        (
            types.auth.SentCodePaymentRequired(
                store_product="p",
                phone_code_hash="h",
                support_email_address="a@b.c",
                support_email_subject="s",
                premium_days=1,
                currency="EUR",
                amount=1,
            ),
            "оплату за SMS",
        ),
        (_sent(types.auth.SentCodeTypeSetUpEmailRequired()), "налаштувати пошту для входу"),
        (errors.FloodWaitError(request=None, capture=3600), "зачекати 3600 с"),
        (errors.PhoneNumberInvalidError(request=None), "номер телефону не розпізнано"),
        (errors.PhoneNumberBannedError(request=None), "заблоковано"),
    ],
)
async def test_undeliverable_codes_abort_with_explanation(response: Any, message: str) -> None:
    client = ScriptedClient(code_responses=[response], sign_in_results=[])
    answers = _answers("+380000000000")

    with pytest.raises(LoginAbortedError, match=message):
        await sign_in_interactively(client, ask=lambda _: next(answers), say=lambda _: None)


async def test_too_many_wrong_codes() -> None:
    client = ScriptedClient(
        code_responses=[_sent(types.auth.SentCodeTypeApp(length=5))],
        sign_in_results=[errors.PhoneCodeInvalidError(request=None)] * 5,
    )
    answers = _answers("+380000000000", *["00000"] * 5)

    with pytest.raises(LoginAbortedError, match="забагато спроб"):
        await sign_in_interactively(client, ask=lambda _: next(answers), say=lambda _: None)


async def test_ctrl_d_cancels() -> None:
    def eof(_: str) -> str:
        raise EOFError

    client = ScriptedClient(code_responses=[], sign_in_results=[])
    with pytest.raises(LoginAbortedError, match="скасовано"):
        await sign_in_interactively(client, ask=eof, say=lambda _: None)
