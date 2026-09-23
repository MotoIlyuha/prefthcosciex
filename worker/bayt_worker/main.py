"""ARQ settings: cron schedule and on-demand jobs.

Start with ``arq bayt_worker.main.WorkerSettings``. Cron jobs run in UTC every few
minutes and decide per user by the user's own time zone (Russia spans 11 zones),
so «05:00» and «20:00» are local times for everyone.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any, ClassVar

from app.config.loader import validate_all
from app.db.session import dispose, session_factory
from app.services import scheduler
from app.services.admin import load_overrides
from app.services.answers import finish_recheck
from app.settings import get_settings
from arq import cron
from arq.connections import RedisSettings
from sqlalchemy.ext.asyncio import AsyncSession

log = logging.getLogger("bayt.worker")
Ctx = dict[str, Any]


async def _with_session(fn: Callable[[AsyncSession], Awaitable[Any]]) -> Any:
    async with session_factory()() as session:
        return await fn(session)


async def morning_plans(ctx: Ctx) -> int:
    return int(await _with_session(scheduler.morning_plans))


async def deliver_due(ctx: Ctx) -> dict[str, int]:
    result: dict[str, int] = await _with_session(scheduler.deliver_due)
    return result


async def evening_reminders(ctx: Ctx) -> int:
    return int(await _with_session(scheduler.evening_reminders))


async def curator_updates(ctx: Ctx) -> int:
    return int(await _with_session(scheduler.curator_updates))


async def weekly(ctx: Ctx) -> int:
    return int(await _with_session(scheduler.weekly))


async def nightly(ctx: Ctx) -> dict[str, int]:
    result: dict[str, int] = await _with_session(scheduler.nightly)
    return result


async def recheck_code(ctx: Ctx, attempt_id: int) -> str:
    """7.5.2 for task 27: the check needs file B, built here rather than in a request."""
    status = str(await _with_session(lambda s: finish_recheck(s, attempt_id)))
    if status == "pending":
        from arq import Retry

        raise Retry(defer=60)  # the runner is down; try again in a minute
    return status


async def build_big_file(ctx: Ctx, instance_id: int) -> bool:
    return bool(await _with_session(lambda s: scheduler.build_big_file(s, instance_id)))


async def deliver_notification(ctx: Ctx, notification_id: int) -> dict[str, int]:
    return await deliver_due(ctx)


async def startup(ctx: Ctx) -> None:
    logging.basicConfig(level=logging.INFO)
    validate_all()
    await _with_session(load_overrides)


async def shutdown(ctx: Ctx) -> None:
    await dispose()


EVERY_5 = set(range(0, 60, 5))


class WorkerSettings:
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    functions: ClassVar[list[Any]] = [recheck_code, build_big_file, deliver_notification]
    cron_jobs: ClassVar[list[Any]] = [
        # Local 05:00 falls on a different UTC minute in every zone: check often.
        cron(morning_plans, minute=EVERY_5, run_at_startup=True),
        cron(deliver_due, minute=set(range(60))),
        cron(evening_reminders, minute={2, 32}),
        cron(curator_updates, minute={7}),
        cron(weekly, minute={12}),
        cron(nightly, hour={0}, minute={20}),
    ]
    on_startup = startup
    on_shutdown = shutdown
    max_jobs = 8
    job_timeout = 600
    max_tries = 5
