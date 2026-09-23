"""Streak rules (design doc 4.3)."""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from app.logic.streak import (
    StreakState,
    buy_freeze,
    easy_day_allowed,
    record_threshold,
    restore,
    restore_price,
    settle,
    vacation_allowed,
)

D0 = date(2026, 10, 1)


def run(days: int, state: StreakState | None = None, start: date = D0) -> StreakState:
    state = state or StreakState()
    for i in range(days):
        state, _ = settle(state, start + timedelta(days=i))
        state, _ = record_threshold(state, start + timedelta(days=i))
    return state


def test_consecutive_days_grow_the_streak() -> None:
    assert run(5).current == 5


def test_recording_the_same_day_twice_is_idempotent() -> None:
    state, _ = record_threshold(StreakState(), D0)
    again, milestones = record_threshold(state, D0)
    assert again.current == 1 and milestones == []


def test_freeze_every_seven_days_capped_at_two() -> None:
    assert run(7).freezes == 1
    assert run(14).freezes == 2
    assert run(28).freezes == 2


def test_missed_day_spends_a_freeze_automatically() -> None:
    state = run(7)
    state, events = settle(state, D0 + timedelta(days=8))
    assert [e.kind for e in events] == ["freeze"]
    assert state.current == 7 and state.freezes == 0


def test_missed_day_without_freeze_loses_the_streak() -> None:
    state = run(3)
    state, events = settle(state, D0 + timedelta(days=4))
    assert [e.kind for e in events] == ["lost"]
    assert state.current == 0 and state.lost_value == 3 and state.best == 3


def test_vacation_days_are_free() -> None:
    state = run(3)
    vacation = frozenset({D0 + timedelta(days=3), D0 + timedelta(days=4)})
    state, events = settle(state, D0 + timedelta(days=5), vacation)
    assert [e.kind for e in events] == ["vacation", "vacation"]
    assert state.current == 3


def test_milestones_are_reported() -> None:
    state = run(6)
    _, milestones = record_threshold(state, D0 + timedelta(days=6))
    assert milestones == [7]


def test_restore_price_grows_within_a_month_and_expires() -> None:
    state = run(5)
    lost_day = D0 + timedelta(days=5)
    state, _ = settle(state, lost_day + timedelta(days=1))
    today = lost_day + timedelta(days=1)
    assert restore_price(state, today) == 80
    restored = restore(state, today)
    assert restored.current == 5
    # Lose it again the same month: the price goes up by 20.
    again, _ = settle(restored, today + timedelta(days=2))
    assert restore_price(again, today + timedelta(days=2)) == 100
    # And it is gone after the 48-hour window.
    assert restore_price(state, lost_day + timedelta(days=5)) is None


def test_buy_freeze_respects_the_cap() -> None:
    state = buy_freeze(buy_freeze(StreakState()))
    assert state.freezes == 2
    with pytest.raises(ValueError):
        buy_freeze(state)


def test_vacation_rules() -> None:
    now = datetime(2026, 10, 1, 12, 0)
    tomorrow = [date(2026, 10, 2), date(2026, 10, 3)]
    assert vacation_allowed(tomorrow, 0, now)
    assert not vacation_allowed([date(2026, 10, 1)], 0, now), "at least a day in advance"
    assert not vacation_allowed(tomorrow, 6, now), "no more than seven days a month"


def test_easy_day_once_a_week() -> None:
    assert easy_day_allowed(0)
    assert not easy_day_allowed(1)
