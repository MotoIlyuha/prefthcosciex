"""Sign-in (12.3): Telegram initData, the Login Widget, one-time links from the bot.

Access tokens live 15 minutes; refresh tokens 30 days and rotate on every use. A
refresh token presented twice means it leaked: every session of the user ends.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError
from app.core.initdata import (
    InitDataError,
    TelegramUser,
    verify_init_data,
    verify_login_widget,
)
from app.core.security import decode, issue_tokens, random_token
from app.db.models import RefreshToken, User, WebLoginToken
from app.services.users import ensure_user, settings_of
from app.settings import get_settings

WEB_LINK_TTL = timedelta(minutes=10)
WIDGET_MAX_AGE = 24 * 3600


async def session_for(session: AsyncSession, user: User, created: bool) -> dict[str, Any]:
    pair = issue_tokens(user.id)
    session.add(
        RefreshToken(jti=pair.refresh_jti, user_id=user.id, expires_at=pair.refresh_expires)
    )
    settings = await settings_of(session, user.id)
    await session.commit()
    return {
        "access_token": pair.access,
        "refresh_token": pair.refresh,
        "expires_in": pair.access_expires_in,
        "created": created,
        "user": {
            "id": user.id,
            "first_name": user.first_name,
            "is_admin": user.is_admin,
            "onboarding_done": settings.onboarding_done,
        },
    }


def _unauthorized(reason: str) -> ApiError:
    return ApiError(401, "bad_init_data", "Не удалось проверить вход через Telegram", reason=reason)


async def telegram(session: AsyncSession, init_data: str) -> dict[str, Any]:
    settings = get_settings()
    try:
        tg = verify_init_data(
            init_data, settings.telegram_bot_token, max_age=settings.telegram_initdata_max_age
        )
    except InitDataError as exc:
        raise _unauthorized(str(exc)) from exc
    user, created = await ensure_user(session, tg)
    result = await session_for(session, user, created)
    result["start_param"] = tg.start_param
    return result


async def login_widget(session: AsyncSession, fields: dict[str, str]) -> dict[str, Any]:
    """The web version (11.10): Telegram Login Widget → the same account."""
    settings = get_settings()
    try:
        tg = verify_login_widget(fields, settings.telegram_bot_token, max_age=WIDGET_MAX_AGE)
    except (InitDataError, ValueError, KeyError) as exc:
        raise _unauthorized(str(exc)) from exc
    user, created = await ensure_user(session, tg)
    return await session_for(session, user, created)


async def create_web_link(session: AsyncSession, tg: TelegramUser) -> str:
    """Called by the bot: a one-time link that signs the user into the web version."""
    user, _ = await ensure_user(session, tg)
    token = random_token(24)
    session.add(
        WebLoginToken(token=token, user_id=user.id, expires_at=datetime.now(UTC) + WEB_LINK_TTL)
    )
    await session.commit()
    return f"{settings_base()}/web/login?token={token}"


def settings_base() -> str:
    return get_settings().public_base_url.rstrip("/")


async def web_link(session: AsyncSession, token: str) -> dict[str, Any]:
    row = await session.get(WebLoginToken, token, with_for_update=True)
    now = datetime.now(UTC)
    if row is None or row.used_at is not None or row.expires_at < now:
        raise ApiError(401, "link_expired", "Ссылка устарела. Попросите новую у бота: /web")
    row.used_at = now
    user = await session.get(User, row.user_id)
    if user is None:
        raise ApiError(401, "link_expired", "Пользователь не найден")
    user.delete_requested_at = None
    return await session_for(session, user, False)


async def refresh(session: AsyncSession, token: str) -> dict[str, Any]:
    try:
        payload = decode(token, "refresh")
    except jwt.PyJWTError as exc:
        raise ApiError(401, "bad_refresh", "Войдите заново") from exc
    row = await session.get(RefreshToken, payload.get("jti", ""), with_for_update=True)
    now = datetime.now(UTC)
    if row is None or row.expires_at < now:
        raise ApiError(401, "bad_refresh", "Войдите заново")
    if row.revoked_at is not None:
        # Reuse of a rotated token: assume theft and end every session (14.1).
        await session.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == row.user_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        await session.commit()
        raise ApiError(401, "refresh_reused", "Сессия завершена из соображений безопасности")
    row.revoked_at = now
    user = await session.get(User, row.user_id)
    if user is None or user.delete_requested_at is not None:
        raise ApiError(401, "bad_refresh", "Войдите заново")
    return await session_for(session, user, False)


async def logout(session: AsyncSession, user_id: int) -> None:
    now = datetime.now(UTC)
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    await session.commit()


async def active_sessions(session: AsyncSession, user_id: int) -> int:
    rows = await session.scalars(
        select(RefreshToken.jti).where(
            RefreshToken.user_id == user_id,
            RefreshToken.revoked_at.is_(None),
            RefreshToken.expires_at > datetime.now(UTC),
        )
    )
    return len(list(rows))
