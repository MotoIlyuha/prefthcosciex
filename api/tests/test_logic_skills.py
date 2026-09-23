"""Skill model, confidence and forecast (design doc 6.1, 6.2, 2.3, 7.5.5)."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.logic.skills import (
    SkillState,
    add_reason,
    colour,
    confidence,
    d_to_difficulty,
    difficulty_to_d,
    forecast,
    forgetting_penalty,
    learning_priority,
    primary_to_test,
    self_score,
    speed_score,
    update,
    win_probability,
)

T = date(2026, 10, 1)


def test_difficulty_scale() -> None:
    assert [difficulty_to_d(d) for d in range(1, 6)] == [700, 875, 1050, 1225, 1400]
    assert all(d_to_difficulty(difficulty_to_d(d)) == d for d in range(1, 6))


def test_elo_step_uses_fast_k_for_the_first_five() -> None:
    state = update(
        SkillState(),
        difficulty=3,
        correct=True,
        attempt_no=1,
        hints_used=0,
        time_ratio=1.0,
        today=T,
    )
    expected = 1000 + 60 * (1 - win_probability(1000, 1050))
    assert state.rating == pytest.approx(expected)


def test_exam_weighs_more() -> None:
    kwargs = {
        "difficulty": 3,
        "correct": True,
        "attempt_no": 1,
        "hints_used": 0,
        "time_ratio": 1.0,
        "today": T,
    }
    plain = update(SkillState(), **kwargs)  # type: ignore[arg-type]
    exam = update(SkillState(), exam=True, **kwargs)  # type: ignore[arg-type]
    assert exam.rating - 1000 == pytest.approx(1.5 * (plain.rating - 1000))


def test_second_try_counts_as_partial() -> None:
    kwargs = {"difficulty": 3, "correct": True, "hints_used": 0, "time_ratio": 1.0, "today": T}
    first = update(SkillState(), attempt_no=1, **kwargs)  # type: ignore[arg-type]
    second = update(SkillState(), attempt_no=2, **kwargs)  # type: ignore[arg-type]
    assert first.rating > second.rating > 1000 - 60


def test_forgetting_lowers_mastery_and_caps_at_150() -> None:
    state = SkillState(rating=1200, last_practiced=T)
    assert forgetting_penalty(10) == 50 and forgetting_penalty(100) == 150
    assert state.mastery(T + timedelta(days=20)) < state.mastery(T)


def test_review_intervals_grow_on_success() -> None:
    state = SkillState()
    reviews = []
    for i in range(4):
        state = update(
            state,
            difficulty=2,
            correct=True,
            attempt_no=1,
            hints_used=0,
            time_ratio=1.0,
            today=T + timedelta(days=i),
        )
        reviews.append((state.next_review - (T + timedelta(days=i))).days)  # type: ignore[operator]
    assert reviews == [5, 12, 30, 30]


def test_speed_and_self_scores() -> None:
    assert speed_score([0.8, 1.0]) == 1.0
    assert speed_score([3.0]) == 0.0
    assert speed_score([2.0]) == pytest.approx(0.5)
    assert self_score(["no_method", "careless", "misread", "time"]) == pytest.approx(0.5)


def test_confidence_formula_weights() -> None:
    state = SkillState(rating=1100, correct_recent=(1, 1, 1, 1, 1), time_ratios=(1.0,))
    value = confidence(1, {"a": state}, T).value
    # 0.6 * 0.5 (rating == exam D) + 0.2 * 1 + 0.1 * 1 + 0.1 * 1
    assert value == pytest.approx(70.0)
    assert colour(value) == "green"


def test_weakest_subtype_decides() -> None:
    strong = SkillState(rating=1400)
    weak = SkillState(rating=800)
    both = confidence(15, {"15.1": strong, "15.2": weak}, T).value
    only_strong = confidence(15, {"15.1": strong}, T).value
    assert both < only_strong


def test_exam_arbiter_caps_confidence() -> None:
    """7.5.5: 9/10 in dailies but 2/6 in the exam — confidence drops to the exam level."""
    state = SkillState(
        rating=1400, correct_recent=(1,) * 10, time_ratios=(1.0,), exam_results=(1, 1, 0, 0, 0, 0)
    )
    result = confidence(9, {"s": state}, T, daily_accuracy=0.9)
    assert result.arbiter_applied
    assert result.value == pytest.approx(100 * 2 / 6, abs=0.1)


def test_reasons_are_validated() -> None:
    assert add_reason(SkillState(), "misread").reasons == ("misread",)
    with pytest.raises(ValueError):
        add_reason(SkillState(), "bored")


@pytest.mark.parametrize(
    ("primary", "test"),
    [(6, 40), (8, 46), (15, 64), (20, 78), (29, 100), (7, 43), (0, 0), (3, 20)],
)
def test_score_scale(primary: float, test: int) -> None:
    assert primary_to_test(primary) == test


def test_forecast_blends_with_recent_exam() -> None:
    from app.logic.skills import Confidence

    confs = [Confidence(t, 50.0, 10) for t in range(1, 28)]
    plain = forecast(confs, total_attempts=100)
    assert plain.primary == pytest.approx(14.5)
    blended = forecast(confs, total_attempts=100, recent_exam_primary=20.5)
    assert blended.primary == pytest.approx(17.5) and blended.from_exam
    assert forecast(confs, total_attempts=10).margin == 2


def test_priority_prefers_cheap_unmastered_core_tasks() -> None:
    cheap = learning_priority(1, 0.0, "A")
    expensive = learning_priority(27, 0.0, "A")
    assert cheap > expensive
    assert learning_priority(1, 90.0, "A") < cheap
    assert learning_priority(15, 0.0, "B", focus=(15,)) > learning_priority(15, 0.0, "B")
