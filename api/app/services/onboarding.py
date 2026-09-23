"""Onboarding (11.2), the placement test (6.5) and the band suggestion."""

from __future__ import annotations

from datetime import UTC, datetime, time
from typing import Any

from egegen.core.types import derive_seed
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.loader import floors
from app.core.errors import ApiError, conflict
from app.db.models import Instance, Placement, Subtype, User
from app.logic import placement as rules
from app.logic import skills as skill_logic
from app.logic.timeutil import study_day, valid_tz
from app.services import events
from app.services import instances as inst_service
from app.services import skills as skill_service
from app.services.answers import on_close
from app.services.floors import open_floor
from app.services.users import settings_of

STEPS = ("hello", "goal", "python", "time", "first_task")
BANDS = frozenset({"A", "B", "C"})
PYTHON_LEVELS = frozenset({"none", "little", "yes"})
SOLVED_FOR_SUGGESTION = 5
BAND_C_RATING = 1150.0
BAND_B_RATING = 980.0


async def update(session: AsyncSession, user: User, data: dict[str, Any]) -> dict[str, Any]:
    """Save one onboarding screen. Every field is optional; validation is strict."""
    settings = await settings_of(session, user.id)
    if "band" in data and data["band"] is not None:
        band = str(data["band"])
        if band == "unknown":
            settings.band, settings.band_pending = "B", True
        elif band in BANDS:
            settings.band, settings.band_pending = band, False
        else:
            raise ApiError(422, "bad_band", "Диапазон: A, B, C или unknown")
    if data.get("python_level") is not None:
        if data["python_level"] not in PYTHON_LEVELS:
            raise ApiError(422, "bad_python", "Python: none, little или yes")
        settings.python_level = data["python_level"]
    if data.get("tz"):
        if not valid_tz(str(data["tz"])):
            raise ApiError(422, "bad_tz", "Неизвестный часовой пояс")
        user.tz = str(data["tz"])
    if data.get("daily_time") is not None:
        value = data["daily_time"]
        settings.daily_time = value if isinstance(value, time) else time.fromisoformat(str(value))
    if data.get("notifications_consent") is not None:
        allowed = bool(data["notifications_consent"])
        settings.notifications = {
            k: (allowed and v) if k != "cur_digest" else v
            for k, v in (settings.notifications or {}).items()
        }
    if data.get("privacy_consent"):
        settings.consent_at = settings.consent_at or datetime.now(UTC)
    if data.get("step") is not None:
        step = int(data["step"])
        if not 0 <= step <= len(STEPS):
            raise ApiError(422, "bad_step", "Шаг онбординга 0–5")
        settings.onboarding_step = max(settings.onboarding_step, step)
        await events.track(
            session,
            "onboarding_step",
            user.id,
            {"step": step, "name": STEPS[min(step, len(STEPS)) - 1] if step else ""},
        )
    if data.get("done"):
        if settings.consent_at is None:
            raise conflict("consent_required", "Нужно согласие на обработку данных")
        settings.onboarding_done = True
    await session.commit()
    return {"step": settings.onboarding_step, "done": settings.onboarding_done}


async def first_task(session: AsyncSession, user: User) -> Instance:
    """Task 1 or 4 at difficulty 1: nobody leaves onboarding without a first win."""
    existing = await session.scalar(
        select(Instance)
        .where(Instance.user_id == user.id, Instance.context == "onboarding")
        .order_by(Instance.id.desc())
        .limit(1)
    )
    if existing is not None and existing.state not in ("failed", "expired"):
        return existing
    serial = int(
        await session.scalar(
            select(func.count())
            .select_from(Instance)
            .where(Instance.user_id == user.id, Instance.context == "onboarding")
        )
        or 0
    )
    task_no = 1 if (user.id + serial) % 2 == 0 else 4
    day = study_day(user.tz)
    row = await inst_service.create(
        session,
        user_id=user.id,
        task_no=task_no,
        subtype=None,
        difficulty=1,
        seed=derive_seed(user.id, day, task_no, serial, slot="onboarding"),
        context="onboarding",
        slot="onboarding",
        tz=user.tz,
    )
    await session.commit()
    return row


async def start_placement(session: AsyncSession, user: User) -> Instance:
    settings = await settings_of(session, user.id)
    if settings.placement_done:
        raise conflict("placement_done", "Стартовый тест уже пройден")
    placement = await session.get(Placement, user.id, with_for_update=True)
    if placement is not None and placement.current_instance_id:
        row = await session.get(Instance, placement.current_instance_id)
        if row is not None and row.state in ("planned", "issued", "attempted"):
            return row
    step = rules.first_step()
    if placement is None:
        placement = Placement(user_id=user.id, step_index=step.index, answered=0, results=[])
        session.add(placement)
    row = await _placement_instance(session, user, step, 0)
    placement.current_instance_id = row.id
    await session.commit()
    return row


async def _placement_instance(
    session: AsyncSession, user: User, step: rules.PlacementStep, answered: int
) -> Instance:
    return await inst_service.create(
        session,
        user_id=user.id,
        task_no=step.task_no,
        subtype=None,
        difficulty=step.difficulty,
        seed=derive_seed(user.id, study_day(user.tz), step.task_no, answered, slot="placement"),
        context="placement",
        slot="placement",
        tz=user.tz,
    )


@on_close("placement")
async def _placement_answered(
    session: AsyncSession, user: User, row: Instance, correct: bool
) -> dict[str, Any]:
    placement = await session.get(Placement, user.id, with_for_update=True)
    if placement is None or placement.finished or placement.current_instance_id != row.id:
        return {}
    placement.answered += 1
    placement.results = [*placement.results, [row.task_no, row.difficulty, correct]]
    current = rules.PlacementStep(placement.step_index, row.task_no, row.difficulty)
    following = rules.next_step(current, correct, placement.answered)
    if following is not None:
        nxt = await _placement_instance(session, user, following, placement.answered)
        placement.step_index = following.index
        placement.current_instance_id = nxt.id
        return {
            "placement": {
                "answered": placement.answered,
                "total": rules.STEPS,
                "next_instance_id": nxt.id,
            }
        }
    return {"placement": await _finish_placement(session, user, placement)}


async def _finish_placement(
    session: AsyncSession, user: User, placement: Placement
) -> dict[str, Any]:
    placement.finished = True
    placement.current_instance_id = None
    results = [(int(t), int(d), bool(ok)) for t, d, ok in placement.results]
    unlocked = rules.floors_to_unlock(results)
    for number in sorted(unlocked):
        if number > 1:
            await open_floor(session, user, number, "placement")
    share = sum(ok for _, _, ok in results) / max(1, len(results))
    rating = skill_logic.rating_from_placement(share)
    covered = {t for f in floors().floors if f.number in unlocked for t in f.tasks}
    subtypes = list(
        await session.execute(
            select(Subtype.id, Subtype.task_no).where(Subtype.task_no.in_(covered))
        )
    )
    await skill_service.seed_rating(
        session, user.id, [(sid, t) for sid, t in subtypes], rating, study_day(user.tz)
    )
    settings = await settings_of(session, user.id)
    settings.placement_done = True
    strong = rules.is_strong(results)
    if strong:
        settings.challenge_enabled = True
    await events.track(
        session,
        "placement_done",
        user.id,
        {"correct": sum(ok for _, _, ok in results), "top_floor": max(unlocked)},
    )
    return {
        "finished": True,
        "floors": sorted(unlocked),
        "challenge": strong,
        "correct": sum(ok for _, _, ok in results),
        "total": len(results),
    }


async def band_suggestion(session: AsyncSession, user: User) -> str | None:
    """After five solved tasks, suggest the band the forecast points at (11.2)."""
    settings = await settings_of(session, user.id)
    if not settings.band_pending:
        return None
    solved = (
        await session.scalar(
            select(func.count())
            .select_from(Instance)
            .where(Instance.user_id == user.id, Instance.state == "solved", Instance.task_no > 0)
        )
        or 0
    )
    if solved < SOLVED_FOR_SUGGESTION:
        return None
    # Five tasks say little about 27 of them, so read the rating the student
    # reached on what they did try rather than the (mostly empty) forecast.
    states = [
        st
        for _, st in (await skill_service.all_states(session, user.id)).values()
        if st.attempts > 0
    ]
    if not states:
        return None
    rating = sum(s.rating for s in states) / len(states)
    if rating >= BAND_C_RATING:
        return "C"
    if rating >= BAND_B_RATING:
        return "B"
    return "A"
