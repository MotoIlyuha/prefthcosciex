"""Exam mode (design doc 8): full / half / block, KEGE-style scoring."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.config.loader import curriculum, economy
from app.logic.skills import primary_to_test

Kind = Literal["full", "half", "block"]


@dataclass(frozen=True, slots=True)
class ExamFormat:
    kind: Kind
    tasks: tuple[int, ...]
    minutes: int
    price: int


def exam_format(kind: Kind, block_tasks: tuple[int, ...] = ()) -> ExamFormat:
    prices = economy().prices
    match kind:
        case "full":
            return ExamFormat("full", tuple(range(1, 28)), 235, prices.exam_full)
        case "half":
            return ExamFormat("half", tuple(range(1, 16)), 60, prices.exam_half)
        case "block":
            if not 1 <= len(block_tasks) <= 5:
                raise ValueError("a block holds one to five tasks")
            minutes = min(30, max(20, sum(curriculum().tasks[t].minutes for t in block_tasks)))
            return ExamFormat("block", block_tasks, minutes, prices.exam_block)
    raise ValueError(kind)


def block_tasks_for_topic(task_no: int) -> tuple[int, ...]:
    """Five instances of one topic: the task repeated with different seeds."""
    return (task_no,) * 5


def score_answer(task_no: int, correct_parts: int) -> int:
    """Points for one answer. Tasks 26 and 27 give 1 point per correct number (2.2)."""
    points = curriculum().tasks[task_no].points
    if points == 2:
        return min(2, correct_parts)
    return 1 if correct_parts >= 1 else 0


@dataclass(frozen=True, slots=True)
class ExamScore:
    primary: int
    test: int
    per_task: dict[int, int]
    lost_most: tuple[int, ...]


def total(per_task: dict[int, int], kind: Kind) -> ExamScore:
    primary = sum(per_task.values())
    tasks = curriculum().tasks
    lost = sorted(
        per_task,
        key=lambda t: (-(tasks[t].points - per_task[t]), -tasks[t].minutes, t),
    )
    lost_most = tuple(t for t in lost if tasks[t].points - per_task[t] > 0)[:3]
    # The test score only exists for the full variant; a half or block has no scale.
    test = primary_to_test(primary) if kind == "full" else 0
    return ExamScore(primary, test, per_task, lost_most)
