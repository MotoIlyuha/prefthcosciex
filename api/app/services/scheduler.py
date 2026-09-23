"""Periodic work run by the ARQ worker (``worker/``): each function is one cron job.

Every function takes ``now`` so tests can move the clock, and handles users one by
one: a failure for one user is logged and never blocks the others.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    CuratorLink,
    DailyPlan,
    DailyStats,
    Instance,
    Notification,
    Streak,
    User,
    UserSettings,
)
from app.logic.curator import FIELDS
from app.logic.rewards import threshold_for
from app.logic.timeutil import local_now, study_day, week_start
from app.services import events
from app.services.daily import build_plan
from app.services.instances import read_asset
from app.services.jobs import enqueue
from app.services.notify import BUTTONS, link, render, schedule
from app.services.privacy import purge_due
from app.services.progress import snapshot_now
from app.services.telegram import TelegramError, send_message

log = logging.getLogger("bayt.scheduler")
ACTIVE_DAYS = 30
EVENING_HOURS = range(18, 22)
WEEKLY_HOURS = range(18, 20)


async def _active_users(session: AsyncSession, now: datetime) -> list[User]:
    rows = await session.scalars(
        select(User)
        .join(UserSettings, UserSettings.user_id == User.id)
        .where(
            User.delete_requested_at.is_(None),
            User.last_seen_at >= now - timedelta(days=ACTIVE_DAYS),
            UserSettings.onboarding_done.is_(True),
        )
        .order_by(User.id)
    )
    return list(rows)


async def morning_plans(session: AsyncSession, now: datetime | None = None) -> int:
    """05:00 local (4.2): build the day's plan, pre-build file B of 27, announce it."""
    moment = now or datetime.now(UTC)
    built = 0
    for user in await _active_users(session, moment):
        day = study_day(user.tz, moment)
        if await session.get(DailyPlan, (user.id, day)) is not None:
            continue
        try:
            plan = await build_plan(session, user, day)
            await session.commit()
        except Exception:
            await session.rollback()
            log.exception("plan failed for user %s", user.id)
            continue
        built += 1
        rows = list(await session.scalars(
            select(Instance).where(Instance.id.in_([i["instance_id"] for i in plan.items]))
        ))
        for row in rows:
            if any(a.get("deferred") for a in row.assets):
                await enqueue("build_big_file", row.id)
        mandatory = [i for i in plan.items if i["mandatory"]]
        titles = ", ".join(
            f"{i['task_no']}‑е" if i["task_no"] else "Python" for i in mandatory
        )
        minutes = max(1, round(sum(i["target_seconds"] for i in mandatory) / 60))
        await schedule(
            session, user.id, "dailies_open", {"tasks": titles, "minutes": minutes},
            dedupe=f"dailies_open:{user.id}:{day.isoformat()}", now=moment,
        )
        await session.commit()
    return built


async def evening_reminders(session: AsyncSession, now: datetime | None = None) -> int:
    """20:00 «порог не достигнут», 22:00 «серия под угрозой» (10)."""
    moment = now or datetime.now(UTC)
    planned = 0
    for user in await _active_users(session, moment):
        if local_now(user.tz, moment).hour not in EVENING_HOURS:
            continue
        day = study_day(user.tz, moment)
        stats = await session.get(DailyStats, (user.id, day))
        if stats is not None and (stats.threshold_met or stats.vacation):
            continue
        earned = stats.coins_earned if stats else 0
        left = max(1, threshold_for(bool(stats and stats.easy_day)) - earned)
        streak = await session.get(Streak, user.id)
        current = streak.current if streak else 0
        # With a streak worth protecting, the last-chance message replaces the 20:00
        # one: two reminders about the same threshold would spend the daily budget.
        kind = "streak_risk" if current >= 3 else "threshold_missed"
        row = await schedule(session, user.id, kind, {"left": left, "streak": current},
                             dedupe=f"{kind}:{user.id}:{day.isoformat()}", now=moment)
        planned += row is not None
    await session.commit()
    return planned


def _still_relevant(kind: str, stats: DailyStats | None) -> bool:
    if kind in ("threshold_missed", "streak_risk"):
        return not (stats and stats.threshold_met)
    return True


async def deliver_due(session: AsyncSession, now: datetime | None = None) -> dict[str, int]:
    """Send every due notification; skip the ones the student made pointless."""
    moment = now or datetime.now(UTC)
    counts = {"sent": 0, "skipped": 0, "failed": 0}
    rows = list(await session.scalars(
        select(Notification)
        .where(Notification.status == "scheduled", Notification.scheduled_at <= moment)
        .order_by(Notification.scheduled_at).limit(500).with_for_update(skip_locked=True)
    ))
    for row in rows:
        user = await session.get(User, row.user_id)
        if user is None:
            continue
        stats = await session.get(DailyStats, (user.id, study_day(user.tz, moment)))
        if not _still_relevant(row.kind, stats):
            row.status = "skipped"
            counts["skipped"] += 1
            continue
        text = render(row.kind, row.payload)
        button = (BUTTONS.get(row.kind, "Открыть «Байт»"), link(row.kind, row.payload))
        try:
            await send_message(user.tg_id, text, button)
        except TelegramError as exc:
            row.status = "failed" if exc.permanent else "scheduled"
            if not exc.permanent:
                row.scheduled_at = moment + timedelta(minutes=10)
            counts["failed"] += 1
            log.warning("notification %s: %s", row.id, exc)
            continue
        row.status = "sent"
        row.sent_at = moment
        counts["sent"] += 1
        await events.track(session, "notification_sent", user.id, {"kind": row.kind})
    await session.commit()
    return counts


async def curator_updates(session: AsyncSession, now: datetime | None = None) -> int:
    """Daily digest at the curator's time, «2 дня без активности» (9.4)."""
    moment = now or datetime.now(UTC)
    rows = await session.execute(
        select(CuratorLink, User)
        .join(User, User.id == CuratorLink.student_id)
        .where(CuratorLink.status == "active")
    )
    planned = 0
    for link_row, student in rows.all():
        curator = await session.get(User, link_row.curator_id)
        if curator is None:
            continue
        local = local_now(curator.tz, moment)
        name = student.first_name or "Ученик"
        if link_row.daily_digest_time is not None and local.hour == link_row.daily_digest_time.hour:
            day = study_day(student.tz, moment)
            stats = await session.get(DailyStats, (student.id, day))
            streak = await session.get(Streak, student.id)
            payload = {
                "name": name,
                "threshold": "достигнут" if stats and stats.threshold_met else "не достигнут",
                "streak": streak.current if streak else 0,
                "link": str(student.id),
            }
            row = await schedule(
                session, curator.id, "cur_digest", payload, now=moment,
                dedupe=f"cur_digest:{link_row.id}:{local.date().isoformat()}",
            )
            planned += row is not None
        idle = moment - student.last_seen_at
        allowed = "coins_by_day" in FIELDS[link_row.access]  # «Прогресс» or above
        if idle >= timedelta(days=2) and allowed:
            row = await schedule(
                session, curator.id, "cur_idle", {"name": name, "link": str(student.id)},
                now=moment,
                dedupe=f"cur_idle:{link_row.id}:{student.last_seen_at.date().isoformat()}",
            )
            planned += row is not None
    await session.commit()
    return planned


async def weekly(session: AsyncSession, now: datetime | None = None) -> int:
    """Sunday 19:00 local: «Итоги недели + план» and the curators' weekly report."""
    moment = now or datetime.now(UTC)
    planned = 0
    for user in await _active_users(session, moment):
        local = local_now(user.tz, moment)
        if local.weekday() != 6 or local.hour not in WEEKLY_HOURS:
            continue
        start = week_start(local.date())
        stats = list(await session.scalars(
            select(DailyStats).where(DailyStats.user_id == user.id, DailyStats.date >= start)
        ))
        streak = await session.get(Streak, user.id)
        payload: dict[str, Any] = {
            "coins": sum(s.coins_earned for s in stats),
            "tasks": sum(s.tasks_done for s in stats),
            "streak": streak.current if streak else 0,
        }
        row = await schedule(session, user.id, "weekly_summary", payload, now=moment,
                             dedupe=f"weekly_summary:{user.id}:{start.isoformat()}")
        planned += row is not None
        await snapshot_now(session, user)
    curators = await session.scalars(
        select(CuratorLink.curator_id).where(CuratorLink.status == "active").distinct()
    )
    for curator_id in list(curators):
        curator = await session.get(User, curator_id)
        if curator is None:
            continue
        local = local_now(curator.tz, moment)
        if local.weekday() != 6 or local.hour not in WEEKLY_HOURS:
            continue
        row = await schedule(session, curator_id, "cur_weekly", {}, now=moment,
                             dedupe=f"cur_weekly:{curator_id}:{local.date().isoformat()}")
        planned += row is not None
    await session.commit()
    return planned


async def nightly(session: AsyncSession, now: datetime | None = None) -> dict[str, int]:
    """Expire overdue instances, snapshot confidence, purge deleted accounts."""
    moment = now or datetime.now(UTC)
    expired = await session.execute(
        update(Instance)
        .where(Instance.state.in_(("planned", "issued", "attempted")),
               Instance.expires_at < moment, Instance.context != "exam")
        .values(state="expired")
    )
    await session.commit()
    snapshots = 0
    for user in await _active_users(session, moment):
        await snapshot_now(session, user)
        snapshots += 1
    await session.commit()
    purged = await purge_due(session, moment)
    return {"expired": int(getattr(expired, "rowcount", 0) or 0), "snapshots": snapshots,
            "purged": purged}


async def build_big_file(session: AsyncSession, instance_id: int) -> bool:
    """File B of 27 (10^6 numbers) ahead of time, so the student never waits (12.4)."""
    row = await session.get(Instance, instance_id)
    if row is None:
        return False
    for asset in row.assets:
        if asset.get("deferred"):
            await read_asset(row, asset["name"])
    return True

