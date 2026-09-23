"""JWT access/refresh tokens (12.3) with refresh rotation (14.1)."""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

from app.settings import get_settings

ALGORITHM = "HS256"


@dataclass(frozen=True, slots=True)
class TokenPair:
    access: str
    refresh: str
    refresh_jti: str
    refresh_expires: datetime
    access_expires_in: int


def issue_tokens(user_id: int, *, now: datetime | None = None) -> TokenPair:
    settings = get_settings()
    moment = now or datetime.now(UTC)
    access_ttl = timedelta(minutes=settings.jwt_access_ttl_min)
    refresh_ttl = timedelta(days=settings.jwt_refresh_ttl_days)
    jti = secrets.token_urlsafe(24)
    access = jwt.encode(
        {"sub": str(user_id), "typ": "access", "iat": moment, "exp": moment + access_ttl},
        settings.jwt_secret,
        algorithm=ALGORITHM,
    )
    refresh = jwt.encode(
        {
            "sub": str(user_id),
            "typ": "refresh",
            "jti": jti,
            "iat": moment,
            "exp": moment + refresh_ttl,
        },
        settings.jwt_secret,
        algorithm=ALGORITHM,
    )
    return TokenPair(access, refresh, jti, moment + refresh_ttl, int(access_ttl.total_seconds()))


def decode(token: str, expected_type: str) -> dict[str, Any]:
    payload: dict[str, Any] = jwt.decode(
        token,
        get_settings().jwt_secret,
        algorithms=[ALGORITHM],
        options={"require": ["exp", "sub"]},
    )
    if payload.get("typ") != expected_type:
        raise jwt.InvalidTokenError("wrong token type")
    return payload


def random_token(nbytes: int = 24) -> str:
    return secrets.token_urlsafe(nbytes)
