"""«Прогресс» (11.6) and «Уверенность» (11.7)."""

from __future__ import annotations

from collections import Counter
from datetime import date, timedelta
from typing import Any

from egegen.core.cards import card_id_for
from sqlalchemy import Integer, cast, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.loader import curriculum, economy
from app.core.errors import ApiError
from app.db.models import (
    Attempt,
    ConfidenceSnapshot,
    DailyStats,
    Instance,
    Streak,
    Subtype,
    User,
    Wallet,
)
from app.logic import skills as skill_logic
from app.logic.rewards import rank_for, threshold_for
from app.logic.timeutil import study_day
from app.services import skills as skill_service
from app.services.curators import _recent_exam_primary
from app.services.daily import focus_tasks
from app.services.users import settings_of

RANGES = {"7d": 7, "30d": 30, "90d": 90, "all": 3650}
REASON_TEXT = {
    "no_method": "не знал, как подступиться",
    "misread": "неправильно понял условие",
    "code_bug": "ошибка в коде",
    "careless": "невнимательность",
    "time": "не хватило времени",
    "format": "формат ответа",
    "forgot": "забыл формулу",
    "other": "другое",
}


async def progress(session: AsyncSession, user: User, range_key: str) -> dict[str, Any]:
    if range_key not in RANGES:
        raise ApiError(422, "bad_range", "Диапазон: 7d, 30d, 90d или all")
    today = study_day(user.tz)
    start = today - timedelta(days=RANGES[range_key] - 1)
    rows = {
        s.date: s
        for s in await session.scalars(
            select(DailyStats).where(DailyStats.user_id == user.id, DailyStats.date >= start)
        )
    }
    if range_key == "all" and rows:
        start = min(rows)
    settings = await settings_of(session, user.id)
    vacation = set(settings.vacation_days or [])
    easy = set(settings.easy_days or [])
    days = []
    cursor = start
    while cursor <= today:
        s = rows.get(cursor)
        iso = cursor.isoformat()
        days.append(
            {
                "date": iso,
                "coins": s.coins_earned if s else 0,
                "tasks": s.tasks_done if s else 0,
                "threshold_met": bool(s and s.threshold_met),
                "easy": iso in easy or bool(s and s.easy_day),
                "vacation": iso in vacation or bool(s and s.vacation),
                "today": cursor == today,
            }
        )
        cursor += timedelta(days=1)
    streak = await session.get(Streak, user.id)
    wallet = await session.get(Wallet, user.id)
    totals = await session.execute(
        select(func.count(), func.coalesce(func.sum(DailyStats.time_spent_s), 0))
        .select_from(DailyStats)
        .where(DailyStats.user_id == user.id, DailyStats.tasks_done > 0)
    )
    active_days, seconds = totals.one()
    solved = (
        await session.scalar(
            select(func.count())
            .select_from(Instance)
            .where(
                Instance.user_id == user.id, Instance.state == "solved", Instance.void.is_(False)
            )
        )
        or 0
    )
    xp = wallet.xp if wallet else 0
    rank, next_xp = rank_for(xp)
    week = _week_pattern(days[-28:])
    return {
        "range": range_key,
        "threshold": threshold_for(False),
        "cap": economy().day.cap,
        "days": days,
        "milestones": economy().streak.milestones,
        "totals": {
            "streak": streak.current if streak else 0,
            "best_streak": streak.best if streak else 0,
            "solved": int(solved),
            "hours": round(int(seconds) / 3600, 1),
            "active_days": int(active_days),
            "rank": rank,
            "xp": xp,
            "next_rank_xp": next_xp,
        },
        "week": week,
    }


def _week_pattern(days: list[dict[str, Any]]) -> list[dict[str, Any]]:
    names = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
    buckets: dict[int, list[int]] = {i: [] for i in range(7)}
    for d in days:
        buckets[date.fromisoformat(d["date"]).weekday()].append(d["tasks"])
    return [
        {"day": names[i], "avg_tasks": round(sum(v) / len(v), 1) if v else 0.0}
        for i, v in buckets.items()
    ]


async def _daily_accuracy(session: AsyncSession, user_id: int) -> dict[int, float]:
    """First-answer accuracy in the dailies per task, for the exam arbiter (7.5.5)."""
    rows = await session.execute(
        select(Instance.task_no, func.avg(cast(Attempt.is_correct, Integer)))
        .join(Attempt, Attempt.instance_id == Instance.id)
        .where(
            Instance.user_id == user_id,
            Instance.context.in_(("daily", "practice")),
            Attempt.no == 1,
            Instance.void.is_(False),
        )
        .group_by(Instance.task_no)
    )
    return {int(t): float(v) for t, v in rows.all() if v is not None}


async def confidence_overview(session: AsyncSession, user: User) -> dict[str, Any]:
    today = study_day(user.tz)
    states = await skill_service.all_states(session, user.id)
    by_task: dict[int, dict[str, skill_logic.SkillState]] = {}
    for sid, (task_no, st) in states.items():
        by_task.setdefault(task_no, {})[sid] = st
    accuracy = await _daily_accuracy(session, user.id)
    week_ago = await snapshot_before(session, user.id, today - timedelta(days=7))
    tasks = curriculum().tasks
    items = []
    confidences = []
    for t in range(1, 28):
        current = skill_logic.confidence(
            t, by_task.get(t, {}), today, daily_accuracy=accuracy.get(t)
        )
        before = float(week_ago.values.get(str(t), current.value)) if week_ago else current.value
        confidences.append(current)
        exam = [r for s in by_task.get(t, {}).values() for r in s.exam_results]
        item: dict[str, Any] = {
            "task_no": t,
            "title": tasks[t].title,
            "points": tasks[t].points,
            "value": current.value,
            "colour": skill_logic.colour(current.value),
            "trend": _trend(current.value, before),
            "attempts": current.attempts,
            "arbiter": current.arbiter_applied,
        }
        if current.arbiter_applied:
            daily = accuracy.get(t, 0.0)
            item["arbiter_note"] = (
                f"В дейликах {round(daily * 10)}/10, на экзамене {sum(exam)}/{len(exam)} — "
                "давай без подсказок"
            )
        items.append(item)
    settings = await settings_of(session, user.id)
    band = curriculum().bands[settings.band]  # type: ignore[index]
    total_attempts = sum(c.attempts for c in confidences)
    fc = skill_logic.forecast(
        confidences,
        total_attempts=total_attempts,
        recent_exam_primary=await _recent_exam_primary(session, user.id),
    )
    await record_snapshot(session, user.id, today, confidences, fc.primary)
    await session.commit()
    return {
        "forecast": {
            "primary": fc.primary,
            "test": fc.test,
            "margin": fc.margin,
            "from_exam": fc.from_exam,
        },
        "band": {"code": settings.band, "title": band.title, "range": list(band.range)},
        "focus": list(await focus_tasks(session, user.id, today)),
        "tasks": items,
    }


async def snapshot_before(
    session: AsyncSession, user_id: int, day: date
) -> ConfidenceSnapshot | None:
    """The latest snapshot taken on or before ``day``."""
    row: ConfidenceSnapshot | None = await session.scalar(
        select(ConfidenceSnapshot)
        .where(ConfidenceSnapshot.user_id == user_id, ConfidenceSnapshot.date <= day)
        .order_by(ConfidenceSnapshot.date.desc())
        .limit(1)
    )
    return row


async def record_snapshot(
    session: AsyncSession,
    user_id: int,
    day: date,
    confidences: list[skill_logic.Confidence],
    primary: float,
) -> None:
    """One row a day: the trend arrows, the curator's risk sort and the north star (15.1)."""
    values = {str(c.task_no): c.value for c in confidences}
    stmt = insert(ConfidenceSnapshot).values(
        user_id=user_id, date=day, values=values, forecast_primary=primary
    )
    await session.execute(
        stmt.on_conflict_do_update(
            index_elements=["user_id", "date"],
            set_={"values": values, "forecast_primary": primary},
        )
    )


async def snapshot_now(session: AsyncSession, user: User) -> float:
    """Compute and store today's snapshot; returns the forecast primary score."""
    today = study_day(user.tz)
    states = await skill_service.all_states(session, user.id)
    by_task: dict[int, dict[str, skill_logic.SkillState]] = {}
    for sid, (task_no, st) in states.items():
        by_task.setdefault(task_no, {})[sid] = st
    confidences = [skill_logic.confidence(t, by_task.get(t, {}), today) for t in range(1, 28)]
    fc = skill_logic.forecast(
        confidences,
        total_attempts=sum(c.attempts for c in confidences),
        recent_exam_primary=await _recent_exam_primary(session, user.id),
    )
    await record_snapshot(session, user.id, today, confidences, fc.primary)
    return fc.primary


def _trend(now: float, before: float) -> str:
    if now - before >= 3:
        return "up"
    if before - now >= 3:
        return "down"
    return "flat"


async def confidence_detail(session: AsyncSession, user: User, task_no: int) -> dict[str, Any]:
    if not 1 <= task_no <= 27:
        raise ApiError(404, "not_found", "Нет такого задания")
    today = study_day(user.tz)
    subtypes = list(
        await session.scalars(
            select(Subtype).where(Subtype.task_no == task_no).order_by(Subtype.id)
        )
    )
    states = await skill_service.all_states(session, user.id)
    reasons: Counter[str] = Counter()
    rows = []
    for sub in subtypes:
        entry = states.get(sub.id)
        state = entry[1] if entry else skill_logic.SkillState()
        reasons.update(state.reasons)
        rows.append(
            {
                "subtype": sub.id,
                "title": sub.title,
                "mastery": round(state.mastery(today) * 100, 1),
                "attempts": state.attempts,
                "next_review": state.next_review,
                "card_id": card_id_for(task_no, sub.id),
            }
        )
    total = sum(reasons.values())
    top = reasons.most_common(1)
    return {
        "task_no": task_no,
        "title": curriculum().tasks[task_no].title,
        "subtypes": rows,
        "reasons": [
            {"code": c, "text": REASON_TEXT[c], "count": n} for c, n in reasons.most_common()
        ],
        "top_reason": (
            f"Чаще всего мешает: {REASON_TEXT[top[0][0]]} — {top[0][1]} из {total}" if top else None
        ),
        "method_card_id": card_id_for(task_no, subtypes[0].id) if subtypes else None,
    }
