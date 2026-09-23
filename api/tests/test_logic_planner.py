"""Daily planner (design doc 6.3) and the reason-driven adjustments (6.4)."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from egegen.core.registry import list_generators

from app.logic.planner import (
    MAX_MANDATORY_SECONDS,
    MIN_MANDATORY_COINS,
    PlanInput,
    SubtypeInfo,
    expected_coins,
    mandatory_seconds,
    pick_difficulty,
    plan,
)
from app.logic.skills import SkillState, add_reason

T = date(2026, 10, 5)


@pytest.fixture(scope="module")
def subtypes() -> list[SubtypeInfo]:
    return [
        SubtypeInfo(sid, g.task_no, g.templates.subtypes[sid].target_seconds, g.requires_code)
        for g in list_generators()
        for sid in g.subtypes
    ]


@pytest.mark.parametrize("floors_open", [{1}, {1, 2, 3}, set(range(1, 14))])
@pytest.mark.parametrize("band", ["A", "B", "C"])
def test_three_mandatory_plus_bonus(
    subtypes: list[SubtypeInfo], floors_open: set[int], band: str
) -> None:
    items = plan(PlanInput(T, band, frozenset(floors_open), subtypes, challenge_enabled=True))
    mandatory = [i for i in items if i.mandatory]
    assert len(mandatory) == 3
    assert len({i.task_no for i in mandatory}) == 3, "one task number per mandatory slot"
    assert mandatory_seconds(items) <= MAX_MANDATORY_SECONDS
    assert expected_coins(items) >= MIN_MANDATORY_COINS, "threshold survives one mistake"
    assert any(i.slot == "repeat" for i in items)
    assert any(i.slot == "challenge" for i in items)


def test_new_slot_is_one_step_easier() -> None:
    state = SkillState(rating=1300)
    assert pick_difficulty(state, T, new_slot=True) == pick_difficulty(state, T, new_slot=False) - 1


@pytest.mark.parametrize("reason", ["misread", "no_method"])
def test_after_misread_next_instance_is_easier(reason: str) -> None:
    """Checklist item: after «не понял условие» the same subtype comes back easier."""
    state = SkillState(rating=1300)
    before = pick_difficulty(state, T, new_slot=False)
    after = pick_difficulty(add_reason(state, reason), T, new_slot=False)
    assert after == before - 1


def test_misread_adds_the_condition_checklist(subtypes: list[SubtypeInfo]) -> None:
    skills = {"1.1_edge_length": add_reason(SkillState(), "misread")}
    items = plan(PlanInput(T, "A", frozenset({1}), subtypes, skills=skills))
    flagged = [i for i in items if i.subtype == "1.1_edge_length"]
    assert flagged and "condition_checklist" in flagged[0].flags


def test_mastered_task_not_repeated_two_days_running(subtypes: list[SubtypeInfo]) -> None:
    skills = {
        s.subtype: SkillState(rating=1300, last_practiced=T - timedelta(days=1))
        for s in subtypes
        if s.task_no == 1
    }
    items = plan(
        PlanInput(T, "A", frozenset({1, 2}), subtypes, skills=skills, yesterday_tasks=(1,))
    )
    assert 1 not in [i.task_no for i in items if i.mandatory]


def test_at_least_one_task_without_code(subtypes: list[SubtypeInfo]) -> None:
    items = plan(PlanInput(T, "C", frozenset(range(1, 14)), subtypes))
    code = {s.subtype for s in subtypes if s.requires_code}
    assert any(i.subtype not in code for i in items if i.mandatory)


def test_beta_generators_only_in_challenge(subtypes: list[SubtypeInfo]) -> None:
    beta = [
        SubtypeInfo(s.subtype, s.task_no, s.target_seconds, s.requires_code, beta=s.task_no == 1)
        for s in subtypes
    ]
    items = plan(PlanInput(T, "A", frozenset({1}), beta, challenge_enabled=True))
    assert all(i.task_no != 1 for i in items if i.mandatory)


def test_easy_day_is_a_single_basic_task(subtypes: list[SubtypeInfo]) -> None:
    items = plan(PlanInput(T, "B", frozenset(range(1, 14)), subtypes, easy_day=True))
    assert len(items) == 1 and items[0].task_no <= 10 and items[0].difficulty == 1


def test_python_minimum_takes_a_slot(subtypes: list[SubtypeInfo]) -> None:
    items = plan(PlanInput(T, "A", frozenset({1, 2}), subtypes, python_exercise_due=True))
    assert items[0].slot == "python"
    assert len([i for i in items if i.mandatory]) == 3


def test_focus_topic_is_preferred(subtypes: list[SubtypeInfo]) -> None:
    items = plan(PlanInput(T, "B", frozenset(range(1, 14)), subtypes, focus_tasks=(15,)))
    assert 15 in [i.task_no for i in items]


def test_review_queue_feeds_the_consolidate_slot(subtypes: list[SubtypeInfo]) -> None:
    due = SkillState(
        rating=1150, last_practiced=T - timedelta(days=6), next_review=T - timedelta(days=1)
    )
    items = plan(PlanInput(T, "A", frozenset({1, 2, 3}), subtypes, skills={"12.1_digit_sum": due}))
    assert "12.1_digit_sum" in [i.subtype for i in items]
