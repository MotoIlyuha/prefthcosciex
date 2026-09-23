"""The day streak (design doc 4.3): freezes, vacation, easy day, restoration.

The state is advanced lazily: whenever the user shows up (or the nightly job runs),
:func:`settle` walks every day between the last one accounted for and yesterday,
spending freezes or vacation on missed days, and :func:`record_threshold` counts a
day in which the threshold was met.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta

from app.config.loader import economy
from app.logic.timeutil import month_key


@dataclass(frozen=True, slots=True)
class StreakState:
    current: int = 0
    best: int = 0
    freezes: int = 0
    last_met: date | None = None
    """Last study day on which the threshold was met."""
    accounted_until: date | None = None
    """Last study day that has been settled (met, frozen, vacationed or lost)."""
    lost_on: date | None = None
    lost_value: int = 0
    """The streak length at the moment it broke — what a restoration brings back."""
    restores_month: str = ""
    restores_used: int = 0
    frozen_days: tuple[date, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class SettleEvent:
    day: date
    kind: str
    """``freeze`` | ``vacation`` | ``lost``"""


def settle(
    state: StreakState,
    today: date,
    vacation_days: frozenset[date] = frozenset(),
) -> tuple[StreakState, list[SettleEvent]]:
    """Account for every study day strictly before ``today`` that has not been yet.

    A missed day inside a vacation keeps the streak for free; otherwise a freeze is
    spent automatically (4.3); with no freeze left the streak is lost and becomes
    restorable for 48 hours.
    """
    events: list[SettleEvent] = []
    if state.last_met is None:
        return replace(state, accounted_until=today - timedelta(days=1)), events

    cursor = (state.accounted_until or state.last_met) + timedelta(days=1)
    frozen = list(state.frozen_days)
    current, freezes = state.current, state.freezes
    lost_on, lost_value = state.lost_on, state.lost_value
    while cursor < today:
        if current > 0:
            if cursor in vacation_days:
                events.append(SettleEvent(cursor, "vacation"))
            elif freezes > 0:
                freezes -= 1
                frozen.append(cursor)
                events.append(SettleEvent(cursor, "freeze"))
            else:
                lost_on, lost_value = cursor, current
                current = 0
                events.append(SettleEvent(cursor, "lost"))
        cursor += timedelta(days=1)
    return (
        replace(
            state,
            current=current,
            freezes=freezes,
            lost_on=lost_on,
            lost_value=lost_value,
            frozen_days=tuple(frozen[-60:]),
            accounted_until=today - timedelta(days=1),
        ),
        events,
    )


def record_threshold(state: StreakState, day: date) -> tuple[StreakState, list[int]]:
    """Count a day on which the threshold was met. Idempotent for the same day.

    Returns the new state and any milestones reached (7, 14, 30, 60, 100), which
    are cosmetic rewards, never coins (4.3).
    """
    rules = economy().streak
    if state.last_met == day:
        return state, []
    current = state.current + 1
    freezes = state.freezes
    if current % rules.freeze_every_days == 0:
        freezes = min(rules.max_freezes, freezes + 1)
    milestones = [m for m in rules.milestones if current == m]
    new = replace(
        state,
        current=current,
        best=max(state.best, current),
        freezes=freezes,
        last_met=day,
        accounted_until=day,
    )
    return new, milestones


def restore_price(state: StreakState, today: date) -> int | None:
    """Price to bring a lost streak back, or ``None`` if it cannot be restored.

    80 coins, +20 for each further restoration in the same month, within 48 hours
    of the loss (4.3, 5.3).
    """
    prices = economy().prices
    if state.lost_on is None or state.current > 0 or state.lost_value <= 0:
        return None
    window_days = prices.restore_window_hours // 24
    if (today - state.lost_on).days > window_days:
        return None
    used = state.restores_used if state.restores_month == month_key(today) else 0
    return prices.restore_base + prices.restore_step * used


def restore(state: StreakState, today: date) -> StreakState:
    if restore_price(state, today) is None:
        raise ValueError("streak cannot be restored")
    month = month_key(today)
    used = state.restores_used if state.restores_month == month else 0
    return replace(
        state,
        current=state.lost_value,
        lost_on=None,
        lost_value=0,
        restores_month=month,
        restores_used=used + 1,
        accounted_until=today - timedelta(days=1),
        last_met=today - timedelta(days=1),
    )


def buy_freeze(state: StreakState) -> StreakState:
    rules = economy().streak
    if state.freezes >= rules.max_freezes:
        raise ValueError("freeze limit reached")
    return replace(state, freezes=state.freezes + 1)


def vacation_allowed(
    requested: list[date], already_this_month: int, now_local: datetime
) -> bool:
    """At most 7 days a month, requested at least a day in advance (4.3)."""
    rules = economy().streak
    if not requested:
        return False
    if min(requested) <= now_local.date():
        return False
    return already_this_month + len(requested) <= rules.vacation_days_per_month


def easy_day_allowed(used_this_week: int) -> bool:
    return used_this_week < economy().streak.easy_days_per_week
