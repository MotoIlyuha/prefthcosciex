"""Placement test (design doc 6.5): eight adaptive steps starting at task 8, d3."""

from __future__ import annotations

from dataclasses import dataclass

# Ladder of (task, difficulty) rungs covering "no code", "Python basics", "games",
# and "В level". A correct answer climbs, a wrong one descends.
LADDER: tuple[tuple[int, int], ...] = (
    (1, 2),
    (4, 2),
    (7, 3),
    (8, 3),
    (2, 3),
    (11, 3),
    (5, 3),
    (14, 3),
    (16, 3),
    (19, 3),
    (20, 3),
    (15, 4),
    (17, 4),
    (13, 4),
    (21, 4),
    (24, 4),
    (27, 4),
)
START_INDEX = 3
STEPS = 8


@dataclass(frozen=True, slots=True)
class PlacementStep:
    index: int
    task_no: int
    difficulty: int


def first_step() -> PlacementStep:
    task, difficulty = LADDER[START_INDEX]
    return PlacementStep(START_INDEX, task, difficulty)


def next_step(current: PlacementStep, correct: bool, answered: int) -> PlacementStep | None:
    if answered >= STEPS:
        return None
    jump = 2 if correct else -2
    index = max(0, min(len(LADDER) - 1, current.index + jump))
    task, difficulty = LADDER[index]
    return PlacementStep(index, task, difficulty)


def floors_to_unlock(results: list[tuple[int, int, bool]]) -> set[int]:
    """Floors whose boss the student would pass: ≥ 2 of 3 correct at difficulty ≥ 4.

    With eight questions we observe at most a few tasks per floor, so a floor opens
    when every task of it that was asked at difficulty ≥ 3 was answered correctly and
    at least one of them was asked (a conservative reading of 6.5).
    """
    from app.config.loader import floors as floor_config

    passed: set[int] = {1}
    for floor in floor_config().floors[:-1]:
        asked = [(t, d, ok) for t, d, ok in results if t in floor.tasks and d >= 3]
        if asked and all(ok for _, _, ok in asked):
            passed.add(floor.number)
    # Floors are sequential: open everything up to the highest passed floor.
    top = max(passed)
    return set(range(1, top + 1))


def is_strong(results: list[tuple[int, int, bool]]) -> bool:
    """Strong students get the daily challenge from day one (4.6)."""
    hard = [ok for t, d, ok in results if t >= 20 and d >= 4]
    return bool(hard) and sum(hard) >= max(1, len(hard) - 1)
