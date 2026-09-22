"""The property sweep every generator must pass (design doc 7.2).

Determinism, answer format, agreement of the two solvers, uniqueness, absence of
unfilled placeholders and the generation-time budget — for every subtype at every
difficulty it declares.
"""

from __future__ import annotations

import pytest

from egegen.core.generator import Generator
from egegen.testing import check_instance

SEEDS = range(4000, 4025)


def test_subtype_properties(generator: Generator, subtype: str) -> None:
    spec = generator.templates.subtypes[subtype]
    lo, hi = spec.difficulty_range
    failures: list[str] = []
    for difficulty in range(lo, hi + 1):
        for seed in SEEDS:
            report = check_instance(generator, seed, difficulty, subtype)
            if not report.ok:
                failures.append(str(report))
    assert not failures, "\n".join(failures[:10])


def test_generation_time_budget(generator: Generator, subtype: str) -> None:
    """Median generation stays well inside the budget, not just the worst case."""
    spec = generator.templates.subtypes[subtype]
    lo, hi = spec.difficulty_range
    times = [
        generator.timed_generate(seed, (lo + hi) // 2, subtype)[1]
        for seed in range(5000, 5020)
    ]
    times.sort()
    median = times[len(times) // 2]
    assert median <= generator.generation_budget_ms, (
        f"t{generator.task_no:02d}/{subtype}: median {median:.0f} ms exceeds "
        f"{generator.generation_budget_ms} ms"
    )


def test_hidden_variant_differs(generator: Generator, subtype: str) -> None:
    """The anti-cheat sibling must be a genuinely different instance (doc 7.5.2)."""
    same_answer = 0
    total = 0
    for seed in range(6000, 6015):
        instance = generator.generate(seed, 3, subtype)
        hidden = generator.generate_hidden(instance)
        assert hidden.seed != instance.seed
        total += 1
        if hidden.answer == instance.answer:
            same_answer += 1
    # Some answers are small integers and will coincide by chance; a hidden variant
    # that *always* matched would make the code re-check worthless.
    assert same_answer < total, (
        f"t{generator.task_no:02d}/{subtype}: hidden variant never changes the answer"
    )


@pytest.mark.parametrize("difficulty", [0, 6, -1])
def test_rejects_invalid_difficulty(generator: Generator, difficulty: int) -> None:
    with pytest.raises(ValueError):
        generator.generate(1, difficulty)
