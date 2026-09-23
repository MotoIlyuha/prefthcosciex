"""Helpers shared by the task generators."""

from __future__ import annotations

from collections.abc import Sequence

from egegen.core.rng import Rng

VERTEX_LETTERS = "АБВГДЕЖЗИКЛМНП"
"""Russian letters used for graph vertices, matching exam convention (no Й, О, Р…)."""

LATIN_VERTEX_LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
"""Latin letters for graph vertices; 26 of them caps the largest graph size."""


def markdown_table(
    header: Sequence[str],
    rows: Sequence[Sequence[object]],
    *,
    blank_zero: bool = False,
) -> str:
    """A GitHub-flavoured Markdown table.

    ``blank_zero`` renders 0 as an empty cell — right for an adjacency matrix where
    zero means "no edge", wrong for a truth table where zero is a value. It is off by
    default so a caller has to opt in.
    """

    def cell(value: object) -> str:
        if value is None or (blank_zero and value == 0):
            return ""
        return str(value)

    head = "| " + " | ".join(str(h) for h in header) + " |"
    sep = "|" + "|".join("---" for _ in header) + "|"
    body = ["| " + " | ".join(cell(c) for c in row) + " |" for row in rows]
    return "\n".join([head, sep, *body])


def plural_ru(n: int, one: str, few: str, many: str) -> str:
    """Russian plural agreement: 1 задача, 2 задачи, 5 задач."""
    n = abs(n) % 100
    if 11 <= n <= 14:
        return many
    match n % 10:
        case 1:
            return one
        case 2 | 3 | 4:
            return few
    return many


def pick_scenario(rng: Rng, scenarios: Sequence[dict[str, str]]) -> dict[str, str]:
    """Deterministically choose a narrative wrapper for a statement."""
    return rng.choice(sorted(scenarios, key=lambda s: s.get("id", "")))


def spread(rng: Rng, lo: int, hi: int, count: int, *, distinct: bool = True) -> list[int]:
    """``count`` values in ``[lo, hi]``, distinct by default."""
    if distinct:
        if hi - lo + 1 < count:
            raise ValueError("range too narrow for the requested count")
        return sorted(rng.sample(range(lo, hi + 1), count))
    return sorted(rng.randint(lo, hi) for _ in range(count))


def difficulty_scaled(difficulty: int, lo: int, hi: int) -> int:
    """Map difficulty 1..5 onto ``[lo, hi]`` linearly."""
    return lo + round((hi - lo) * (difficulty - 1) / 4)
