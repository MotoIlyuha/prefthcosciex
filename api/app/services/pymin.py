"""Python-minimum track in the dailies (design doc 6.3.6, Appendix C)."""

from __future__ import annotations

import hashlib
from datetime import date

from egegen.pymin import LESSONS, generate
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.db.models import Attempt, Instance, User
from app.logic.timeutil import day_bounds

EXERCISES_PER_LESSON = 3
PASS_SHARE = 0.8


async def progress(session: AsyncSession, user_id: int) -> tuple[int, int, int]:
    """(solved exercises, solved at first try, current lesson)."""
    solved = (
        await session.scalar(
            select(func.count())
            .select_from(Instance)
            .where(Instance.user_id == user_id, Instance.task_no == 0, Instance.state == "solved")
        )
        or 0
    )
    first_try = (
        await session.scalar(
            select(func.count())
            .select_from(Attempt)
            .join(Instance, Instance.id == Attempt.instance_id)
            .where(
                Instance.user_id == user_id,
                Instance.task_no == 0,
                Attempt.no == 1,
                Attempt.is_correct.is_(True),
            )
        )
        or 0
    )
    lesson = min(len(LESSONS), solved // EXERCISES_PER_LESSON + 1)
    return int(solved), int(first_try), lesson


def track_complete(solved: int, first_try: int) -> bool:
    """80 % of exercises solved at first try across all eight lessons (Appendix C)."""
    total = len(LESSONS) * EXERCISES_PER_LESSON
    return solved >= total and first_try >= PASS_SHARE * solved


async def create_exercise(session: AsyncSession, user: User, day: date, seed: int) -> Instance:
    _, _, lesson = await progress(session, user.id)
    exercise = await run_in_threadpool(generate, lesson, seed)
    _, expires = day_bounds(user.tz, day)
    row = Instance(
        user_id=user.id,
        task_no=0,
        subtype_id=f"py.lesson{lesson}",
        difficulty=1,
        seed=seed,
        hidden_seed=exercise.hidden_seed,
        gen_version="pymin-1",
        context="daily",
        slot="python",
        mandatory=True,
        statement_md=exercise.statement_md,
        assets=[],
        answer=exercise.answer,
        answer_hash=hashlib.sha256(f"{seed}|{exercise.answer}".encode()).hexdigest(),
        answer_kind="int",
        checker="exact",
        checker_options={},
        solution_steps=[exercise.explanation],
        reference_code=exercise.code,
        method_card_id="py:minimum",
        target_seconds=300,
        exam_like=False,
        requires_code=False,
        flags=["python_minimum"],
        state="planned",
        planned_for=day,
        expires_at=expires,
        meta={"lesson": lesson},
    )
    session.add(row)
    await session.flush()
    return row
