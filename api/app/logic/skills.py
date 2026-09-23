"""The skill model (design doc 6.1–6.2): Elo per subtype, mastery with forgetting,
the confidence scale per task and the score forecast (2.3)."""

from __future__ import annotations

import itertools
import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field, replace
from datetime import date, timedelta

from app.config.loader import curriculum

START_RATING = 1000.0
EXAM_D = 1100.0
REVIEW_INTERVALS = (2, 5, 12, 30)
REASONS = ("no_method", "misread", "code_bug", "careless", "time", "format", "forgot", "other")


def difficulty_to_d(difficulty: int) -> float:
    """Difficulty 1..5 maps onto 700..1400 (6.1)."""
    return 700.0 + (difficulty - 1) * 175.0


def d_to_difficulty(d: float) -> int:
    return max(1, min(5, round((d - 700.0) / 175.0) + 1))


def win_probability(rating: float, d: float) -> float:
    return 1.0 / (1.0 + 10 ** ((d - rating) / 400.0))


def forgetting_penalty(days_idle: int) -> float:
    return float(min(150, 5 * max(0, days_idle)))


@dataclass(frozen=True, slots=True)
class SkillState:
    rating: float = START_RATING
    attempts: int = 0
    correct_recent: tuple[int, ...] = ()
    """Last results, newest last: 1 correct first try, 0 otherwise."""
    last_practiced: date | None = None
    review_step: int = 0
    next_review: date | None = None
    time_ratios: tuple[float, ...] = ()
    reasons: tuple[str, ...] = field(default_factory=tuple)
    """Last difficulty reasons (6.4), newest last."""
    exam_results: tuple[int, ...] = ()

    def effective_rating(self, today: date) -> float:
        if self.last_practiced is None:
            return self.rating
        return self.rating - forgetting_penalty((today - self.last_practiced).days)

    def mastery(self, today: date) -> float:
        """Probability to solve an exam-level instance (6.1)."""
        return win_probability(self.effective_rating(today), EXAM_D)


def result_score(correct: bool, attempt_no: int, hints_used: int) -> float:
    """1 for a clean first try, 0.6 for a second try or with a hint, 0 otherwise."""
    if not correct:
        return 0.0
    if attempt_no == 1 and hints_used == 0:
        return 1.0
    if attempt_no <= 2:
        return 0.6
    return 0.0


def update(
    state: SkillState,
    *,
    difficulty: int,
    correct: bool,
    attempt_no: int,
    hints_used: int,
    time_ratio: float | None,
    today: date,
    exam: bool = False,
    weight: float = 1.0,
) -> SkillState:
    """One Elo step (6.1). ``weight`` < 1 is used when the method check failed (7.5.3)."""
    d = difficulty_to_d(difficulty)
    expected = win_probability(state.rating, d)
    score = result_score(correct, attempt_no, hints_used)
    k = 60.0 if state.attempts < 5 else 30.0
    if exam:
        k *= 1.5
    rating = state.rating + k * weight * (score - expected)

    recent = (*state.correct_recent, 1 if score == 1.0 else 0)[-10:]
    ratios = state.time_ratios if time_ratio is None else (*state.time_ratios, time_ratio)
    # Spaced repetition (6.1): each clean success pushes the next review further.
    step = min(state.review_step + 1, len(REVIEW_INTERVALS) - 1) if score == 1.0 else 0
    exam_results = (*state.exam_results, 1 if correct else 0) if exam else state.exam_results
    return replace(
        state,
        rating=rating,
        attempts=state.attempts + 1,
        correct_recent=recent,
        last_practiced=today,
        review_step=step,
        next_review=today + timedelta(days=REVIEW_INTERVALS[step]),
        time_ratios=ratios[-10:],
        exam_results=exam_results[-20:],
    )


def add_reason(state: SkillState, reason: str) -> SkillState:
    if reason not in REASONS:
        raise ValueError(f"unknown reason {reason!r}")
    return replace(state, reasons=(*state.reasons, reason)[-10:])


def speed_score(ratios: Sequence[float]) -> float:
    """1 at or under the target time, falling linearly to 0 at three times it."""
    if not ratios:
        return 0.5
    avg = sum(ratios) / len(ratios)
    if avg <= 1.0:
        return 1.0
    return max(0.0, 1.0 - (avg - 1.0) / 2.0)


def self_score(reasons: Sequence[str]) -> float:
    """1 minus the share of recent struggles blamed on "no method" or "misread"."""
    recent = list(reasons)[-10:]
    if not recent:
        return 1.0
    bad = sum(1 for r in recent if r in ("no_method", "misread"))
    return 1.0 - bad / len(recent)


@dataclass(frozen=True, slots=True)
class Confidence:
    task_no: int
    value: float
    """0..100"""
    attempts: int
    arbiter_applied: bool = False


def confidence(
    task_no: int,
    subtype_states: dict[str, SkillState],
    today: date,
    *,
    daily_accuracy: float | None = None,
) -> Confidence:
    """confidence = 0.6·mastery_exam + 0.2·acc_recent5 + 0.1·speed + 0.1·self (6.2).

    ``mastery_exam`` is the *weakest* subtype: the exam does not let you pick.
    The exam arbiter (7.5.5): if the daily accuracy on this task is above 85% but
    the exam accuracy is below 40% over at least six exam answers, confidence is
    capped at the exam level.
    """
    if not subtype_states:
        return Confidence(task_no, 0.0, 0)
    states = list(subtype_states.values())
    mastery = min(s.mastery(today) for s in states)
    recent = [r for s in states for r in s.correct_recent][-5:]
    acc = sum(recent) / len(recent) if recent else 0.0
    ratios = [r for s in states for r in s.time_ratios]
    reasons = [r for s in states for r in s.reasons]
    value = 100.0 * (
        0.6 * mastery + 0.2 * acc + 0.1 * speed_score(ratios) + 0.1 * self_score(reasons)
    )
    attempts = sum(s.attempts for s in states)

    exam = [r for s in states for r in s.exam_results]
    arbiter = False
    if daily_accuracy is not None and len(exam) >= 6:
        exam_acc = sum(exam) / len(exam)
        if daily_accuracy > 0.85 and exam_acc < 0.40:
            value = min(value, 100.0 * exam_acc)
            arbiter = True
    return Confidence(task_no, round(value, 1), attempts, arbiter)


def colour(value: float) -> str:
    if value < 40:
        return "red"
    if value < 70:
        return "yellow"
    return "green"


def primary_to_test(primary: float) -> int:
    """Primary points → test score by the 2.3 table, interpolating between rows.

    Below the 6-point minimum the score scales linearly from 0 (decision D‑017).
    """
    scale = sorted(curriculum().score_scale.items())
    if primary <= 0:
        return 0
    low_primary, low_test = scale[0]
    if primary < low_primary:
        return round(low_test * primary / low_primary)
    for (p1, t1), (p2, t2) in itertools.pairwise(scale):
        if p1 <= primary <= p2:
            return round(t1 + (t2 - t1) * (primary - p1) / (p2 - p1))
    return scale[-1][1]


@dataclass(frozen=True, slots=True)
class Forecast:
    primary: float
    test: int
    margin: int
    """± primary points (2 while there are fewer than 30 attempts)."""
    from_exam: bool


def forecast(
    confidences: Iterable[Confidence],
    *,
    total_attempts: int,
    recent_exam_primary: float | None = None,
) -> Forecast:
    """Expected primary = Σ points(t) × confidence(t)/100 (6.2).

    With an exam in the last 30 days the forecast is blended 50/50 with it (8).
    """
    tasks = curriculum().tasks
    primary = sum(tasks[c.task_no].points * c.value / 100.0 for c in confidences)
    from_exam = recent_exam_primary is not None
    if recent_exam_primary is not None:
        primary = 0.5 * primary + 0.5 * recent_exam_primary
    margin = 2 if total_attempts < 30 else 1
    primary = round(primary, 1)
    return Forecast(primary, primary_to_test(primary), margin, from_exam)


def learning_priority(
    task_no: int,
    confidence_value: float,
    band: str,
    focus: Sequence[int] = (),
) -> float:
    """priority = points × (1 − confidence) × band_weight / learning_cost (3.2)."""
    cur = curriculum()
    band_info = cur.bands[band]  # type: ignore[index]
    weights = cur.band_weight
    if task_no in focus:
        weight = weights.focus
    elif task_no in band_info.core:
        weight = weights.core
    elif task_no in band_info.bonus:
        weight = weights.bonus
    else:
        weight = weights.other
    points = cur.tasks[task_no].points
    cost = cur.learning_cost[task_no]
    return points * (1.0 - confidence_value / 100.0) * weight / cost


def rating_from_placement(correct_share: float) -> float:
    """Starting rating from the placement test (6.5): 1000 ± up to 250."""
    return START_RATING + 500.0 * (correct_share - 0.5)


def expected_score_bounds() -> tuple[int, int]:
    return 0, math.floor(sum(t.points for t in curriculum().tasks.values()))
