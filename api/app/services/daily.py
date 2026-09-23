"""Daily plans and the «Сегодня» screen (design doc 4.2, 6.3, 11.3)."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

from egegen.core.types import derive_seed
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.loader import curriculum, economy
from app.db.models import (
    CuratorFocus,
    CuratorLink,
    DailyPlan,
    DailyStats,
    Instance,
    Subtype,
    User,
    UserFloor,
    UserSettings,
    Wallet,
)
from app.logic.planner import PlanInput, SubtypeInfo, plan
from app.logic.rewards import RewardInput, rank_for, reward, threshold_for
from app.logic.timeutil import study_day, week_start
from app.services import instances as inst_service
from app.services import skills as skill_service
from app.services.streaks import settle_today
from app.services.users import settings_of


async def subtype_catalogue(session: AsyncSession) -> list[SubtypeInfo]:
    today = datetime.now(UTC).date()
    rows = await session.scalars(select(Subtype).order_by(Subtype.id))
    return [
        SubtypeInfo(
            r.id,
            r.task_no,
            r.target_seconds,
            r.requires_code,
            beta=bool(r.beta and (r.beta_until is None or r.beta_until >= today)),
        )
        for r in rows
    ]


async def unlocked_floors(session: AsyncSession, user_id: int) -> set[int]:
    rows = await session.scalars(
        select(UserFloor.floor_id).where(UserFloor.user_id == user_id, UserFloor.state != "locked")
    )
    return set(rows) | {1}


async def focus_tasks(session: AsyncSession, user_id: int, day: date) -> tuple[int, ...]:
    rows = await session.scalars(
        select(CuratorFocus.task_nos)
        .join(CuratorLink, CuratorLink.id == CuratorFocus.link_id)
        .where(
            CuratorLink.student_id == user_id,
            CuratorLink.status == "active",
            CuratorFocus.week_start == week_start(day),
        )
    )
    return tuple(sorted({t for tasks in rows for t in tasks}))


async def stats_for(session: AsyncSession, user_id: int, day: date) -> DailyStats:
    row = await session.get(DailyStats, (user_id, day), with_for_update=True)
    if row is None:
        row = DailyStats(
            user_id=user_id,
            date=day,
            coins_earned=0,
            coins_capped=0,
            tasks_done=0,
            threshold_met=False,
            easy_day=False,
            vacation=False,
            time_spent_s=0,
            xp=0,
            feedback_bonuses=0,
            free_reveals_used=0,
            similar_counts={},
        )
        session.add(row)
        await session.flush()
    return row


async def build_plan(session: AsyncSession, user: User, day: date) -> DailyPlan:
    existing = await session.get(DailyPlan, (user.id, day))
    if existing is not None:
        return existing
    settings = await settings_of(session, user.id)
    states = {
        sid: st for sid, (_, st) in (await skill_service.all_states(session, user.id)).items()
    }
    yesterday = await session.get(DailyPlan, (user.id, day - timedelta(days=1)))
    floors_open = await unlocked_floors(session, user.id)
    easy = day.isoformat() in (settings.easy_days or [])
    items = plan(
        PlanInput(
            today=day,
            band=settings.band,
            unlocked_floors=frozenset(floors_open),
            subtypes=await subtype_catalogue(session),
            skills=states,
            focus_tasks=await focus_tasks(session, user.id, day),
            yesterday_tasks=tuple(i["task_no"] for i in (yesterday.items if yesterday else [])),
            easy_day=easy,
            challenge_enabled=settings.challenge_enabled or max(floors_open) >= 6,
            python_exercise_due=(
                settings.python_level == "none"
                and not settings.python_track_done
                and max(floors_open) >= 2
            ),
        )
    )
    stored: list[dict[str, Any]] = []
    for index, entry in enumerate(items):
        task_no = entry.task_no
        seed = derive_seed(user.id, day, task_no, 0, slot=f"{index}:{entry.slot}")
        if entry.slot == "python":
            row = await _python_instance(session, user, day, seed)
        else:
            row = await inst_service.create(
                session,
                user_id=user.id,
                task_no=task_no,
                subtype=entry.subtype,
                difficulty=entry.difficulty,
                seed=seed,
                context="daily",
                slot=entry.slot,
                mandatory=entry.mandatory,
                planned_for=day,
                tz=user.tz,
                flags=list(entry.flags),
            )
        stored.append(
            {
                "slot": entry.slot,
                "task_no": task_no,
                "subtype": row.subtype_id,
                "difficulty": entry.difficulty,
                "mandatory": entry.mandatory,
                "target_seconds": row.target_seconds,
                "instance_id": row.id,
                "flags": list(entry.flags),
            }
        )
    daily = DailyPlan(user_id=user.id, date=day, items=stored)
    session.add(daily)
    stats = await stats_for(session, user.id, day)
    stats.easy_day = easy
    await session.flush()
    return daily


async def _python_instance(session: AsyncSession, user: User, day: date, seed: int) -> Instance:
    from app.services.pymin import create_exercise

    return await create_exercise(session, user, day, seed)


def expected_reward(item: dict[str, Any]) -> int:
    if item["task_no"] == 0:
        return 0
    return reward(RewardInput(item["task_no"], item["difficulty"], 1, slot=item["slot"]))


async def today_view(session: AsyncSession, user: User) -> dict[str, Any]:
    day = study_day(user.tz)
    streak = await settle_today(session, user.id, day)
    daily = await build_plan(session, user, day)
    stats = await stats_for(session, user.id, day)
    wallet = await session.get(Wallet, user.id)
    assert wallet is not None
    settings = await session.get(UserSettings, user.id)
    instance_ids = [i["instance_id"] for i in daily.items]
    rows = {
        r.id: r
        for r in await session.scalars(select(Instance).where(Instance.id.in_(instance_ids)))
    }
    day_rules = economy().day
    tasks = curriculum().tasks
    items = []
    for item in daily.items:
        row = rows.get(item["instance_id"])
        items.append(
            {
                **item,
                "title": tasks[item["task_no"]].title if item["task_no"] else "Python‑минимум",
                "state": row.state if row else "expired",
                "minutes": max(1, round(item["target_seconds"] / 60)),
                "reward": expected_reward(item),
            }
        )
    rank, next_rank = rank_for(wallet.xp)
    open_mandatory = [
        i for i in items if i["mandatory"] and i["state"] in ("planned", "issued", "attempted")
    ]
    pending_reveal = await session.scalar(
        select(Instance.id)
        .where(
            Instance.user_id == user.id,
            Instance.planned_for == day,
            Instance.state == "failed",
            Instance.revealed.is_(False),
        )
        .limit(1)
    )
    await session.commit()
    return {
        "day": day.isoformat(),
        "streak": {"current": streak.current, "best": streak.best, "freezes": streak.freezes},
        "wallet": {
            "balance": wallet.balance,
            "xp": wallet.xp,
            "rank": rank,
            "next_rank_xp": next_rank,
        },
        "progress": {
            "earned": stats.coins_earned,
            "threshold": threshold_for(stats.easy_day),
            "cap": day_rules.cap,
            "threshold_met": stats.threshold_met,
            "cap_reached": stats.coins_earned >= day_rules.cap,
            "easy_day": stats.easy_day,
        },
        "items": items,
        "free_practice": stats.coins_earned >= day_rules.cap,
        "free_reveal_available": stats.free_reveals_used < economy().prices.free_reveals_per_day,
        "reveal_candidate": pending_reveal,
        "all_done": not open_mandatory,
        "next_open_at": (
            datetime.combine(day + timedelta(days=1), datetime.min.time())
            .replace(hour=day_rules.day_starts_at_hour)
            .isoformat()
        ),
        "show_timer": bool(settings and settings.show_timer),
    }
