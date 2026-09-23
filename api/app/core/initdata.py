"""Telegram authentication (design doc 12.3).

Mini App: ``secret = HMAC_SHA256(key="WebAppData", msg=bot_token)``, then
``hash == HMAC_SHA256(secret, data_check_string)`` where the data-check string is
every field except ``hash``, sorted by key, joined as ``key=value`` with newlines.

Login Widget (web version): ``secret = SHA256(bot_token)`` over the same kind of
string. Both reject payloads older than the configured maximum age.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qsl


class InitDataError(ValueError):
    """The payload is malformed, forged or stale. Never tell the client which."""


@dataclass(frozen=True, slots=True)
class TelegramUser:
    id: int
    first_name: str
    username: str | None
    language_code: str | None
    start_param: str | None = None


def _check_string(fields: dict[str, str]) -> str:
    return "\n".join(f"{k}={fields[k]}" for k in sorted(fields) if k != "hash")


def sign_init_data(fields: dict[str, str], bot_token: str) -> str:
    """Produce the ``hash`` for a payload — used by tests and the dev login helper."""
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    return hmac.new(secret, _check_string(fields).encode(), hashlib.sha256).hexdigest()


def verify_init_data(
    raw: str, bot_token: str, *, max_age: int, now: float | None = None
) -> TelegramUser:
    if not bot_token:
        raise InitDataError("bot token is not configured")
    fields = dict(parse_qsl(raw, keep_blank_values=True, strict_parsing=False))
    received = fields.get("hash", "")
    if not received:
        raise InitDataError("missing hash")
    expected = sign_init_data(fields, bot_token)
    if not hmac.compare_digest(expected, received):
        raise InitDataError("bad signature")
    try:
        auth_date = int(fields.get("auth_date", "0"))
    except ValueError as exc:
        raise InitDataError("bad auth_date") from exc
    current = time.time() if now is None else now
    if auth_date <= 0 or current - auth_date > max_age or auth_date - current > 60:
        raise InitDataError("stale auth_date")
    try:
        user: dict[str, Any] = json.loads(fields.get("user", ""))
        return TelegramUser(
            id=int(user["id"]),
            first_name=str(user.get("first_name", ""))[:128],
            username=user.get("username"),
            language_code=user.get("language_code"),
            start_param=fields.get("start_param"),
        )
    except (ValueError, KeyError, TypeError) as exc:
        raise InitDataError("bad user payload") from exc


def sign_login_widget(fields: dict[str, str], bot_token: str) -> str:
    secret = hashlib.sha256(bot_token.encode()).digest()
    return hmac.new(secret, _check_string(fields).encode(), hashlib.sha256).hexdigest()


def verify_login_widget(
    fields: dict[str, str], bot_token: str, *, max_age: int, now: float | None = None
) -> TelegramUser:
    if not bot_token:
        raise InitDataError("bot token is not configured")
    received = fields.get("hash", "")
    if not received or not hmac.compare_digest(sign_login_widget(fields, bot_token), received):
        raise InitDataError("bad signature")
    current = time.time() if now is None else now
    auth_date = int(fields.get("auth_date", "0") or 0)
    if auth_date <= 0 or current - auth_date > max_age:
        raise InitDataError("stale auth_date")
    return TelegramUser(
        id=int(fields["id"]),
        first_name=fields.get("first_name", "")[:128],
        username=fields.get("username"),
        language_code=None,
    )
