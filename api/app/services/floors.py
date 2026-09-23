"""The «Путь» screen: floors, unlocking with coins, extern and boss (3.3, 5.3, 5.5, 11.5)."""

from __future__ import annotations

import random
from datetime import UTC, datetime
from typing import Any

from egegen.core.types import derive_seed
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.loader import curriculum, economy, floors
from app.core.errors import ApiError, conflict, forbidden, not_found
from app.db.models import FloorTrial, Instance, User, UserFloor
from app.logic import skills as skill_logic
from app.logic.timeutil import study_day
from app.services import events
from app.services import instances as inst_service
from app.services import skills as skill_service
from app.services import wallet as wallet_service
from app.services.answers import on_close
from app.services.curators import notify_curators
from app.services.notify import schedule
from app.services.users import settings_of

MASTERED = 70.0


def floor_config(number: int) -> Any:
    for floor in floors().floors:
        if floor.number == number:
            return floor
    raise not_found("этаж")


async def _states(session: AsyncSession, user_id: int) -> dict[int, str]:
    rows = await session.execute(
        select(UserFloor.floor_id, UserFloor.state).where(UserFloor.user_id == user_id)
    )
    return {int(f): str(s) for f, s in rows.all()}


async def confidences(session: AsyncSession, user_id: int) -> dict[int, skill_logic.Confidence]:
    states = await skill_service.all_states(session, user_id)
    today = datetime.now(UTC).date()
    by_task: dict[int, dict[str, skill_logic.SkillState]] = {}
    for sid, (task_no, state) in states.items():
        by_task.setdefault(task_no, {})[sid] = state
    return {t: skill_logic.confidence(t, by_task.get(t, {}), today) for t in range(1, 28)}


async def path_view(session: AsyncSession, user: User) -> dict[str, Any]:
    settings = await settings_of(session, user.id)
    states = await _states(session, user.id)
    conf = await confidences(session, user.id)
    required = set(floors().required_floors[settings.band])  # type: ignore[index]
    day = study_day(user.tz)
    extern_used = await _trial_today(session, user.id, day, "extern")
    tasks_info = curriculum().tasks
    result = []
    current = 1
    for floor in floors().floors:
        state = states.get(floor.number, "locked")
        if state != "locked":
            current = floor.number
        mastered = sum(1 for t in floor.tasks if conf[t].value >= MASTERED)
        result.append(
            {
                "number": floor.number,
                "title": floor.title,
                "python": floor.python,
                "state": state,
                "required": floor.number in required,
                "price": economy().prices.floor(floor.number),
                "mastered": mastered,
                "total": len(floor.tasks),
                "tasks": [
                    {
                        "task_no": t,
                        "title": tasks_info[t].title,
                        "confidence": conf[t].value,
                        "colour": skill_logic.colour(conf[t].value),
                    }
                    for t in floor.tasks
                ],
                "boss_passed": state == "boss_passed",
            }
        )
    return {
        "band": settings.band,
        "current": current,
        "extern_available": extern_used is None,
        "floors": result,
    }


async def _trial_today(
    session: AsyncSession, user_id: int, day: Any, kind: str, floor_no: int | None = None
) -> FloorTrial | None:
    query = select(FloorTrial).where(
        FloorTrial.user_id == user_id, FloorTrial.day == day, FloorTrial.kind == kind
    )
    if floor_no is not None:
        query = query.where(FloorTrial.floor_id == floor_no)
    trial: FloorTrial | None = await session.scalar(query.limit(1))
    return trial


async def open_floor(session: AsyncSession, user: User, number: int, by: str) -> bool:
    """Mark a floor unlocked. Returns True when it was closed before."""
    stmt = (
        insert(UserFloor)
        .values(user_id=user.id, floor_id=number, state="unlocked", unlocked_by=by)
        .on_conflict_do_nothing(index_elements=["user_id", "floor_id"])
        .returning(UserFloor.floor_id)
    )
    created = await session.scalar(stmt)
    if created is None:
        row = await session.get(UserFloor, (user.id, number))
        if row is None or row.state != "locked":
            return False
        row.state = "unlocked"
        row.unlocked_by = by
    floor = floor_config(number)
    await events.track(session, "floor_unlocked", user.id, {"floor": number, "by": by})
    how = {"extern": " — экстерн засчитан", "placement": " по стартовому тесту"}.get(by, "")
    await schedule(
        session,
        user.id,
        "floor_unlocked",
        {"floor": number, "title": floor.title, "how": how, "link": str(number)},
        dedupe=f"floor_unlocked:{user.id}:{number}",
    )
    await notify_curators(session, user, "cur_floor", {"floor": number, "title": floor.title})
    return True


async def unlock(session: AsyncSession, user: User, number: int) -> dict[str, Any]:
    floor_config(number)
    states = await _states(session, user.id)
    if states.get(number, "locked") != "locked":
        raise conflict("already_open", "Этаж уже открыт")
    if number > 1 and states.get(number - 1, "locked") == "locked":
        raise conflict("previous_locked", "Сначала откройте предыдущий этаж")
    price = economy().prices.floor(number)
    await wallet_service.move(
        session,
        user.id,
        -price,
        reason="floor_unlock",
        key=f"floor:{user.id}:{number}",
        ref_type="floor",
        ref_id=number,
    )
    await open_floor(session, user, number, "coins")
    await events.track(session, "shop_buy", user.id, {"item": "floor", "price": price})
    await session.commit()
    return {"floor": number, "price": price}


async def start_trial(session: AsyncSession, user: User, number: int, kind: str) -> dict[str, Any]:
    """Three tasks of the floor at exam difficulty; 3 of 3 passes (extern) / boss."""
    floor = floor_config(number)
    if number == 1 and kind == "extern":
        raise conflict("not_applicable", "Первый этаж открыт всегда")
    states = await _states(session, user.id)
    state = states.get(number, "locked")
    day = study_day(user.tz)
    if kind == "extern":
        if state != "locked":
            raise conflict("already_open", "Этаж уже открыт")
        if await _trial_today(session, user.id, day, "extern") is not None:
            raise ApiError(429, "extern_used", "Экстерн — один раз в сутки. Завтра можно снова.")
        rules = floors().extern
    else:
        if state == "locked":
            raise forbidden("Сначала откройте этаж")
        if await _trial_today(session, user.id, day, "boss", number) is not None:
            raise ApiError(429, "boss_used", "Босса этого этажа можно пройти раз в сутки")
        rules = floors().boss  # type: ignore[assignment]
    if len(floor.tasks) > rules.tasks:
        # The final floor holds all 27: draw three distinct ones, reproducibly.
        picker = random.Random(derive_seed(user.id, day, number, 0, slot=f"{kind}:pick"))
        task_nos = sorted(picker.sample(list(floor.tasks), rules.tasks))
    else:
        task_nos = [floor.tasks[i % len(floor.tasks)] for i in range(rules.tasks)]
    trial = FloorTrial(user_id=user.id, floor_id=number, kind=kind, day=day, instance_ids=[])
    session.add(trial)
    await session.flush()
    rows: list[Instance] = []
    for index, task_no in enumerate(task_nos):
        seed = derive_seed(user.id, day, task_no, index + 1, slot=f"{kind}:{number}")
        row = await inst_service.create(
            session,
            user_id=user.id,
            task_no=task_no,
            subtype=None,
            difficulty=rules.difficulty,
            seed=seed,
            context=kind,
            slot=kind,
            tz=user.tz,
        )
        row.meta = {**row.meta, "trial_id": trial.id}
        rows.append(row)
    trial.instance_ids = [r.id for r in rows]
    await session.commit()
    return {
        "trial_id": trial.id,
        "kind": kind,
        "floor": number,
        "instances": [inst_service.public(r) for r in rows],
    }


async def trial_view(session: AsyncSession, user: User, trial_id: int) -> dict[str, Any]:
    trial = await session.get(FloorTrial, trial_id)
    if trial is None or trial.user_id != user.id:
        raise not_found("испытание")
    rows = {
        r.id: r
        for r in await session.scalars(select(Instance).where(Instance.id.in_(trial.instance_ids)))
    }
    return {
        "trial_id": trial.id,
        "kind": trial.kind,
        "floor": trial.floor_id,
        "correct": trial.correct,
        "finished": trial.finished,
        "passed": trial.passed,
        "instances": [inst_service.public(rows[i]) for i in trial.instance_ids if i in rows],
    }


async def _close_trial(
    session: AsyncSession, user: User, row: Instance, correct: bool
) -> dict[str, Any]:
    trial = await session.get(FloorTrial, int(row.meta.get("trial_id", 0)), with_for_update=True)
    if trial is None:
        return {}
    if correct:
        trial.correct += 1
    siblings = list(
        await session.scalars(select(Instance).where(Instance.id.in_(trial.instance_ids)))
    )
    closed = [s for s in siblings if s.state in ("solved", "failed", "revealed", "expired")]
    result: dict[str, Any] = {
        "trial_id": trial.id,
        "kind": trial.kind,
        "correct": trial.correct,
        "total": len(siblings),
        "finished": len(closed) == len(siblings),
    }
    if len(closed) < len(siblings) or trial.finished:
        return result
    trial.finished = True
    need = floors().extern.tasks if trial.kind == "extern" else floors().boss.pass_needed
    trial.passed = trial.correct >= need
    result["passed"] = trial.passed
    if trial.kind == "extern":
        await events.track(
            session, "extern_result", user.id, {"floor": trial.floor_id, "passed": trial.passed}
        )
        if trial.passed:
            await open_floor(session, user, trial.floor_id, "extern")
    elif trial.passed:
        uf = await session.get(UserFloor, (user.id, trial.floor_id))
        if uf is not None:
            uf.state = "boss_passed"
    return result


on_close("extern")(_close_trial)
on_close("boss")(_close_trial)
