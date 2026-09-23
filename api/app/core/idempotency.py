"""``Idempotency-Key`` for mutations (12.5): a replay returns the first response."""

from __future__ import annotations

import json
from typing import Any

from app.core.ratelimit import redis

TTL_S = 24 * 3600


async def recall(user_id: int, key: str | None) -> dict[str, Any] | None:
    if not key:
        return None
    raw = await redis().get(f"idem:{user_id}:{key}")
    return None if raw is None else dict(json.loads(raw))


async def remember(user_id: int, key: str | None, response: dict[str, Any]) -> None:
    if key:
        await redis().set(f"idem:{user_id}:{key}", json.dumps(response, default=str), ex=TTL_S)
