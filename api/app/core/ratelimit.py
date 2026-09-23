"""Fixed-window rate limits in Redis (12.6): answers per minute, code runs per hour."""

from __future__ import annotations

import time

from redis.asyncio import Redis

from app.core.errors import ApiError
from app.settings import get_settings

_redis: Redis | None = None


def redis() -> Redis:
    global _redis
    if _redis is None:
        _redis = Redis.from_url(get_settings().redis_url, decode_responses=True)
    return _redis


async def close() -> None:
    global _redis
    if _redis is not None:
        await _redis.aclose()
    _redis = None


async def hit(bucket: str, key: str, limit: int, window_s: int) -> None:
    """Count one request; raise 429 when the window's budget is spent."""
    window = int(time.time() // window_s)
    name = f"rl:{bucket}:{key}:{window}"
    client = redis()
    count = await client.incr(name)
    if count == 1:
        await client.expire(name, window_s + 5)
    if count > limit:
        raise ApiError(
            429, "rate_limited", "Слишком часто. Попробуйте чуть позже.", retry_after=window_s
        )
