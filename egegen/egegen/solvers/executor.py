"""Program counting for the abstract executor of task 13 (design doc, Appendix A)."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from functools import lru_cache

COMMAND_LIBRARY: dict[str, tuple[str, Callable[[int], int], bool]] = {
    # id -> (Russian label, transform, monotone-increasing?)
    "add1": ("прибавить 1", lambda x: x + 1, True),
    "add2": ("прибавить 2", lambda x: x + 2, True),
    "add3": ("прибавить 3", lambda x: x + 3, True),
    "mul2": ("умножить на 2", lambda x: x * 2, True),
    "mul3": ("умножить на 3", lambda x: x * 3, True),
    "sub1": ("вычесть 1", lambda x: x - 1, False),
    "sub2": ("вычесть 2", lambda x: x - 2, False),
}


def command_label(cmd_id: str) -> str:
    return COMMAND_LIBRARY[cmd_id][0]


def is_monotone(commands: Sequence[str]) -> bool:
    return all(COMMAND_LIBRARY[c][2] for c in commands)


def count_programs(a: int, b: int, commands: Sequence[str]) -> int:
    """Number of command sequences taking ``a`` to ``b``.

    The empty program counts when ``a == b`` (doc trap: ``f(x, x) = 1``). Only valid
    for monotone increasing command sets, where states above ``b`` are dead ends.
    """
    fns = [COMMAND_LIBRARY[c][1] for c in commands]

    @lru_cache(maxsize=None)
    def f(x: int) -> int:
        if x > b:
            return 0
        if x == b:
            return 1
        return sum(f(fn(x)) for fn in fns)

    return f(a)


def count_programs_bounded(
    a: int,
    b: int,
    commands: Sequence[str],
    *,
    lo: int,
    hi: int,
    max_len: int,
) -> int:
    """Program counting for non-monotone command sets.

    With subtraction available the state graph has cycles, so the count is only
    finite under an explicit length bound and a value range — exactly how the exam
    phrases such variants.
    """
    fns = [COMMAND_LIBRARY[c][1] for c in commands]

    @lru_cache(maxsize=None)
    def f(x: int, steps_left: int) -> int:
        if x == b:
            # The program may stop here, or keep going and come back.
            rest = (
                sum(f(fn(x), steps_left - 1) for fn in fns if lo <= fn(x) <= hi)
                if steps_left > 0
                else 0
            )
            return 1 + rest
        if steps_left == 0:
            return 0
        return sum(f(fn(x), steps_left - 1) for fn in fns if lo <= fn(x) <= hi)

    return f(a, max_len)


def count_programs_naive(a: int, b: int, commands: Sequence[str], max_len: int = 24) -> int:
    """Breadth-first enumeration of programs — the independent cross-check."""
    fns = [COMMAND_LIBRARY[c][1] for c in commands]
    total = 0
    frontier = [a]
    if a == b:
        total += 1
    for _ in range(max_len):
        nxt: list[int] = []
        for x in frontier:
            for fn in fns:
                y = fn(x)
                if y > b:
                    continue
                if y == b:
                    total += 1
                else:
                    nxt.append(y)
        if not nxt:
            break
        frontier = nxt
    return total


def count_through(a: int, c: int, b: int, commands: Sequence[str]) -> int:
    return count_programs(a, c, commands) * count_programs(c, b, commands)


def count_avoiding(a: int, b: int, c: int, commands: Sequence[str]) -> int:
    """Programs that never pass through ``c``.

    Subtraction is valid only for monotone commands, where ``c`` can be visited at
    most once (doc trap).
    """
    return count_programs(a, b, commands) - count_through(a, c, b, commands)


def count_through_not_through(
    a: int, c: int, d: int, b: int, commands: Sequence[str]
) -> int:
    """Programs through ``c`` but avoiding ``d`` (``c < d`` is assumed by the caller)."""
    return count_programs(a, c, commands) * count_avoiding(c, b, d, commands)


def trajectory_reaches(a: int, b: int, commands: Sequence[str], target: int) -> bool:
    return count_through(a, target, b, commands) > 0
