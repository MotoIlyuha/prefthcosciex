"""Persistence for the skill model; the maths lives in :mod:`app.logic.skills`."""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import SkillStateRow
from app.logic.skills import SkillState


def to_state(row: SkillStateRow) -> SkillState:
    return SkillState(
        rating=row.rating,
        attempts=row.attempts_n,
        correct_recent=tuple(row.correct_recent or ()),
        last_practiced=row.last_practiced,
        review_step=row.review_step,
        next_review=row.next_review,
        time_ratios=tuple(row.time_ratios or ()),
        reasons=tuple(row.reasons or ()),
        exam_results=tuple(row.exam_results or ()),
    )


def write_state(row: SkillStateRow, state: SkillState) -> None:
    row.rating = state.rating
    row.attempts_n = state.attempts
    row.correct_recent = list(state.correct_recent)
    row.last_practiced = state.last_practiced
    row.review_step = state.review_step
    row.next_review = state.next_review
    row.time_ratios = list(state.time_ratios)
    row.reasons = list(state.reasons)
    row.exam_results = list(state.exam_results)


async def row_for(session: AsyncSession, user_id: int, subtype: str, task_no: int) -> SkillStateRow:
    row = await session.get(SkillStateRow, (user_id, subtype))
    if row is None:
        row = SkillStateRow(
            user_id=user_id,
            subtype_id=subtype,
            task_no=task_no,
            rating=1000.0,
            attempts_n=0,
            correct_recent=[],
            time_ratios=[],
            reasons=[],
            exam_results=[],
            review_step=0,
        )
        session.add(row)
        await session.flush()
    return row


async def all_states(session: AsyncSession, user_id: int) -> dict[str, tuple[int, SkillState]]:
    rows = await session.scalars(select(SkillStateRow).where(SkillStateRow.user_id == user_id))
    return {r.subtype_id: (r.task_no, to_state(r)) for r in rows}


async def seed_rating(
    session: AsyncSession, user_id: int, subtypes: list[tuple[str, int]], rating: float, today: date
) -> None:
    """Initial ratings from the placement test (6.5)."""
    for subtype, task_no in subtypes:
        row = await row_for(session, user_id, subtype, task_no)
        if row.attempts_n == 0:
            row.rating = rating
            row.last_practiced = today
