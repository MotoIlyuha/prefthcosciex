"""Helpers shared by the routers: idempotent mutations and per-user rate limits."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Annotated, Any

from fastapi import Depends, Header

from app.core import idempotency
from app.core.deps import CurrentUser
from app.core.ratelimit import hit
from app.db.models import User
from app.settings import get_settings

IdemKey = Annotated[str | None, Header(alias="Idempotency-Key", max_length=128)]


async def idempotent(
    user_id: int, key: str | None, action: Callable[[], Awaitable[dict[str, Any]]]
) -> dict[str, Any]:
    """Run a mutation once per ``Idempotency-Key``; a replay gets the first response."""
    cached = await idempotency.recall(user_id, key)
    if cached is not None:
        return cached
    result = await action()
    await idempotency.remember(user_id, key, result)
    return result


async def default_limit(user: CurrentUser) -> User:
    await hit("req", str(user.id), get_settings().rate_limit_default_per_min, 60)
    return user


async def answer_limit(user: CurrentUser) -> User:
    """60 answers a minute (12.6); with three attempts per task, guessing is pointless."""
    await hit("answer", str(user.id), get_settings().rate_limit_answers_per_min, 60)
    return user


async def run_limit(user: CurrentUser) -> User:
    """20 server-side runs an hour (12.6)."""
    await hit("run", str(user.id), get_settings().rate_limit_runs_per_hour, 3600)
    return user


LimitedUser = Annotated[User, Depends(default_limit)]
AnsweringUser = Annotated[User, Depends(answer_limit)]
RunningUser = Annotated[User, Depends(run_limit)]
