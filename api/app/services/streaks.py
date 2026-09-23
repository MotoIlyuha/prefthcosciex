"""Streak persistence around :mod:`app.logic.streak`."""

from __future__ import annotations

from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Streak, UserSettings
from app.logic.streak import StreakState, record_threshold, settle


def to_state(row: Streak) -> StreakState:
    return StreakState(
        current=row.current,
        best=row.best,
        freezes=row.freezes,
        last_met=row.last_met_date,
        accounted_until=row.accounted_until,
        lost_on=row.lost_on,
        lost_value=row.lost_value,
        restores_month=row.restores_month,
        restores_used=row.recovered_this_month,
        frozen_days=tuple(date.fromisoformat(d) for d in row.frozen_days or []),
    )


def write(row: Streak, state: StreakState) -> None:
    row.current = state.current
    row.best = state.best
    row.freezes = state.freezes
    row.last_met_date = state.last_met
    row.accounted_until = state.accounted_until
    row.lost_on = state.lost_on
    row.lost_value = state.lost_value
    row.restores_month = state.restores_month
    row.recovered_this_month = state.restores_used
    row.frozen_days = [d.isoformat() for d in state.frozen_days]


async def row_for(session: AsyncSession, user_id: int) -> Streak:
    row = await session.get(Streak, user_id, with_for_update=True)
    if row is None:
        row = Streak(user_id=user_id)
        session.add(row)
        await session.flush()
    return row


async def settle_today(session: AsyncSession, user_id: int, today: date) -> Streak:
    row = await row_for(session, user_id)
    settings = await session.get(UserSettings, user_id)
    vacation = frozenset(
        date.fromisoformat(d) for d in (settings.vacation_days if settings else [])
    )
    state, _ = settle(to_state(row), today, vacation)
    write(row, state)
    return row


async def mark_threshold(session: AsyncSession, user_id: int, day: date) -> list[int]:
    row = await settle_today(session, user_id, day)
    state, milestones = record_threshold(to_state(row), day)
    write(row, state)
    return milestones
