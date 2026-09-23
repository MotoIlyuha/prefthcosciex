"""Python-minimum exercises: the computed answer must equal what the program prints."""

from __future__ import annotations

import pytest

from egegen.pymin import LESSONS, execute, generate


@pytest.mark.parametrize("lesson", sorted(LESSONS))
def test_answer_matches_execution(lesson: int) -> None:
    for seed in range(200):
        exercise = generate(lesson, seed)
        assert execute(exercise.code) == exercise.answer, (lesson, seed, exercise.code)


def test_eight_lessons() -> None:
    assert sorted(LESSONS) == list(range(1, 9))


def test_deterministic() -> None:
    assert generate(3, 42).code == generate(3, 42).code


def test_unknown_lesson() -> None:
    with pytest.raises(ValueError):
        generate(9, 1)
