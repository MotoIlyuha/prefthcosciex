"""FastAPI dependencies: database session, current user, role checks."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Annotated

import jwt
from fastapi import Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApiError, forbidden
from app.core.security import decode
from app.db.models import User
from app.db.session import session_factory

LAST_SEEN_RESOLUTION = timedelta(minutes=5)


async def db() -> AsyncIterator[AsyncSession]:
    async with session_factory()() as session:
        yield session


Session = Annotated[AsyncSession, Depends(db)]


async def current_user(
    request: Request,
    session: Session,
    authorization: Annotated[str | None, Header()] = None,
) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise ApiError(401, "unauthorized", "Нужна авторизация")
    try:
        payload = decode(authorization[7:], "access")
    except jwt.ExpiredSignatureError as exc:
        raise ApiError(401, "token_expired", "Сессия истекла") from exc
    except jwt.PyJWTError as exc:
        raise ApiError(401, "unauthorized", "Недействительный токен") from exc
    user = await session.get(User, int(payload["sub"]))
    if user is None or user.delete_requested_at is not None:
        raise ApiError(401, "unauthorized", "Пользователь не найден")
    now = datetime.now(UTC)
    if now - user.last_seen_at > LAST_SEEN_RESOLUTION:
        user.last_seen_at = now
        await session.commit()
    request.state.user_id = user.id
    return user


CurrentUser = Annotated[User, Depends(current_user)]


async def admin_user(user: CurrentUser) -> User:
    if not user.is_admin:
        raise forbidden("Только для администраторов")
    return user


AdminUser = Annotated[User, Depends(admin_user)]
