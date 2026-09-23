"""Liveness and readiness."""

from __future__ import annotations

from typing import Any

from egegen.core.fipi import load_fipi_config
from egegen.core.registry import list_generators
from fastapi import APIRouter
from sqlalchemy import text

from app.config.loader import economy
from app.core.deps import Session
from app.core.ratelimit import redis
from app.settings import get_settings

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(session: Session) -> dict[str, Any]:
    await session.execute(text("select 1"))
    pong = await redis().ping()
    return {
        "status": "ok",
        "db": True,
        "redis": bool(pong),
        "generators": len(list_generators()),
        "season": economy().season_id,
        "fipi": load_fipi_config().version,
    }


@router.get("/config/public")
async def public_config() -> dict[str, Any]:
    """What the web version needs before sign-in: the bot for the login redirect."""
    settings = get_settings()
    head = settings.telegram_bot_token.split(":", 1)[0]
    return {
        "bot_username": settings.telegram_bot_username,
        "bot_id": int(head) if head.isdigit() else None,
        "fipi_banner": None if load_fipi_config().approved else load_fipi_config().banner_ru,
    }
