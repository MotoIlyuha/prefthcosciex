"""Background jobs: the API enqueues, the ARQ worker (``worker/``) executes.

Job names are the worker's function names. Tests install a recorder with
:func:`set_enqueuer` so no worker is needed to exercise the API.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings

from app.settings import get_settings

JOBS = frozenset(
    {
        "recheck_code",  # 7.5.2: re-run a student's program on the hidden variant
        "build_big_file",  # 12.4: file B of task 27, prepared ahead of time
        "deliver_notification",
        "export_user",  # 12.7: data export within 24 hours
        "notify_curators",
    }
)

Enqueuer = Callable[[str, tuple[Any, ...]], Awaitable[None]]
_pool: ArqRedis | None = None
_override: Enqueuer | None = None


def set_enqueuer(fn: Enqueuer | None) -> None:
    global _override
    _override = fn


async def _arq_pool() -> ArqRedis:
    global _pool
    if _pool is None:
        _pool = await create_pool(RedisSettings.from_dsn(get_settings().redis_url))
    return _pool


async def enqueue(name: str, *args: Any) -> None:
    if name not in JOBS:
        raise ValueError(f"unknown job {name!r}")
    if _override is not None:
        await _override(name, args)
        return
    pool = await _arq_pool()
    await pool.enqueue_job(name, *args)


async def close() -> None:
    global _pool
    if _pool is not None:
        await _pool.aclose()
    _pool = None
