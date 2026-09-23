"""Notifications (10), curator access (9), exam scoring (8), placement (6.5), time (4.2)."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta

import pytest

from app.logic.curator import FIELDS, NUDGES, downgrade_ok, risk_score, visible
from app.logic.exam import exam_format, score_answer, total
from app.logic.notify import decide, deep_link, in_quiet_hours
from app.logic.placement import STEPS, first_step, floors_to_unlock, is_strong, next_step
from app.logic.timeutil import day_bounds, study_day, zone

NOW = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)  # 15:00 in Moscow


# -- time ------------------------------------------------------------------
def test_study_day_starts_at_five_local() -> None:
    before = datetime(2026, 10, 5, 1, 30, tzinfo=UTC)  # 04:30 Moscow
    after = datetime(2026, 10, 5, 2, 30, tzinfo=UTC)  # 05:30 Moscow
    assert study_day("Europe/Moscow", before) == date(2026, 10, 4)
    assert study_day("Europe/Moscow", after) == date(2026, 10, 5)


def test_study_day_depends_on_zone() -> None:
    moment = datetime(2026, 10, 5, 20, 0, tzinfo=UTC)
    assert study_day("Asia/Vladivostok", moment) == date(2026, 10, 6)
    assert study_day("Europe/Kaliningrad", moment) == date(2026, 10, 5)


def test_day_bounds_are_24_hours() -> None:
    start, end = day_bounds("Asia/Yekaterinburg", date(2026, 10, 5))
    assert end - start == timedelta(days=1)
    assert start.astimezone(zone("Asia/Yekaterinburg")).hour == 5


def test_unknown_zone_falls_back() -> None:
    assert study_day("Not/AZone", NOW) == study_day("Europe/Moscow", NOW)


# -- notifications ------------------------------------------------------------
def base(**kw: object) -> dict[str, object]:
    args: dict[str, object] = {
        "now": NOW,
        "tz": "Europe/Moscow",
        "enabled": True,
        "sent_today": 0,
        "last_seen": NOW,
        "streak": 5,
    }
    args.update(kw)
    return args


def test_daily_limit_of_two() -> None:
    assert decide("floor_unlocked", **base(sent_today=1)).send  # type: ignore[arg-type]
    assert not decide("floor_unlocked", **base(sent_today=2)).send  # type: ignore[arg-type]


def test_quiet_hours_defer_to_eight() -> None:
    night = datetime(2026, 10, 5, 21, 30, tzinfo=UTC)  # 00:30 Moscow
    decision = decide("exam_checked", **base(now=night))  # type: ignore[arg-type]
    assert decision.send and decision.at is not None
    local = decision.at.astimezone(zone("Europe/Moscow"))
    assert local.time() == time(8, 0)
    assert in_quiet_hours(datetime(2026, 10, 5, 23, 30))
    assert not in_quiet_hours(datetime(2026, 10, 5, 8, 0))


def test_scheduled_kinds_use_local_time() -> None:
    decision = decide("threshold_missed", **base(tz="Asia/Novosibirsk"))  # type: ignore[arg-type]
    assert decision.at is not None
    assert decision.at.astimezone(zone("Asia/Novosibirsk")).time() == time(20, 0)


def test_dailies_open_uses_the_chosen_time() -> None:
    decision = decide("dailies_open", **base(dailies_time=time(17, 30)))  # type: ignore[arg-type]
    assert decision.at is not None
    assert decision.at.astimezone(zone("Europe/Moscow")).time() == time(17, 30)


def test_streak_risk_needs_three_days() -> None:
    assert not decide("streak_risk", **base(streak=2)).send  # type: ignore[arg-type]
    assert decide("streak_risk", **base(streak=3)).send  # type: ignore[arg-type]


def test_opt_out_and_inactivity() -> None:
    assert not decide("weekly_summary", **base(enabled=False)).send  # type: ignore[arg-type]
    gone = NOW - timedelta(days=31)
    assert not decide("dailies_open", **base(last_seen=gone)).send  # type: ignore[arg-type]
    idle = NOW - timedelta(days=15)
    recent_ping = NOW - timedelta(days=2)
    assert not decide(
        "dailies_open",
        **base(last_seen=idle, last_weekly_ping=recent_ping),  # type: ignore[arg-type]
    ).send


def test_deep_link() -> None:
    assert deep_link("bayt_bot", "floor_unlocked") == "https://t.me/bayt_bot/app?startapp=path"


# -- curator -------------------------------------------------------------------
CARD = {
    "student_id": 1,
    "name": "Никита",
    "streak": 5,
    "threshold_today": True,
    "rank": "Байт",
    "coins_by_day": [],
    "confidence": {},
    "forecast": {},
    "exams": [],
    "subtypes": {},
    "reasons": {},
    "attempts": [],
    "time_spent": 0,
    "free_text": "секрет",
}


@pytest.mark.parametrize("access", ["fact", "progress", "full"])
def test_access_levels_project_the_card(access: str) -> None:
    view = visible(CARD, access)  # type: ignore[arg-type]
    assert set(view) - {"student_id", "name"} == set(FIELDS[access])  # type: ignore[index]
    assert "free_text" not in view, "free text never reaches a curator (14.3)"


def test_levels_are_nested() -> None:
    assert FIELDS["fact"] < FIELDS["progress"] < FIELDS["full"]
    assert downgrade_ok("full", "fact") and not downgrade_ok("fact", "full")


def test_six_preset_nudges() -> None:
    assert len(NUDGES) == 6


def test_risk_score_orders_students() -> None:
    assert risk_score(5, 20, True) > risk_score(0, 0, False) == 0


# -- exam ------------------------------------------------------------------------
def test_formats() -> None:
    full = exam_format("full")
    assert (len(full.tasks), full.minutes, full.price) == (27, 235, 150)
    half = exam_format("half")
    assert (half.tasks, half.minutes, half.price) == (tuple(range(1, 16)), 60, 60)
    block = exam_format("block", (17,) * 5)
    assert 20 <= block.minutes <= 30 and block.price == 30


def test_two_point_tasks() -> None:
    assert score_answer(27, 2) == 2 and score_answer(27, 1) == 1 and score_answer(1, 1) == 1


def test_full_exam_scoring() -> None:
    per_task = {t: (2 if t in (26, 27) else 1) for t in range(1, 28)}
    assert total(per_task, "full").test == 100
    per_task[27] = 0
    per_task[24] = 0
    result = total(per_task, "full")
    assert result.primary == 26 and result.test == 93
    assert result.lost_most[0] == 27


# -- placement --------------------------------------------------------------------
def test_placement_starts_at_task_8_and_adapts() -> None:
    step = first_step()
    assert (step.task_no, step.difficulty) == (8, 3)
    harder = next_step(step, True, 1)
    easier = next_step(step, False, 1)
    assert harder is not None and easier is not None
    assert harder.index > step.index > easier.index
    assert next_step(step, True, STEPS) is None


def test_placement_unlocks_floors_sequentially() -> None:
    results = [(1, 3, True), (8, 3, True), (5, 3, True), (16, 3, True), (19, 3, True)]
    assert floors_to_unlock(results) == set(range(1, 8))
    assert floors_to_unlock([(8, 3, False)]) == {1}


def test_strong_student_detection() -> None:
    assert is_strong([(21, 4, True), (24, 4, True)])
    assert not is_strong([(8, 3, True)])
