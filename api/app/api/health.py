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
