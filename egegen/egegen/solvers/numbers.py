"""Number-theory and positional-notation helpers (tasks 5, 7, 8, 11, 14, 25)."""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence

DIGITS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def to_base(n: int, base: int) -> str:
    """Positional representation of a non-negative integer, digits above 9 as letters."""
    if base < 2 or base > 36:
        raise ValueError("base must be in 2..36")
    if n == 0:
        return "0"
    if n < 0:
        raise ValueError("to_base expects a non-negative integer")
    out: list[str] = []
    while n:
        out.append(DIGITS[n % base])
        n //= base
    return "".join(reversed(out))


def from_base(text: str, base: int) -> int:
    return int(text, base)


def digit_sum(text: str, base: int = 10) -> int:
    return sum(DIGITS.index(ch) for ch in text.upper())


def divisors(n: int) -> list[int]:
    """All divisors of ``n``, via the sqrt sweep the exam template uses."""
    if n <= 0:
        raise ValueError("divisors expects a positive integer")
    found: set[int] = set()
    for d in range(1, math.isqrt(n) + 1):
        if n % d == 0:
            found.add(d)
            found.add(n // d)
    return sorted(found)


def divisors_naive(n: int) -> list[int]:
    """Full linear sweep — the independent cross-check of :func:`divisors`."""
    return [d for d in range(1, n + 1) if n % d == 0]


def bits_per_symbol(alphabet_size: int) -> int:
    """Minimum whole bits per symbol: ceil(log2 K) (doc, task 7/11 method)."""
    if alphabet_size < 1:
        raise ValueError("alphabet size must be positive")
    if alphabet_size == 1:
        return 0
    return math.ceil(math.log2(alphabet_size))


def bytes_for_bits(bits: int) -> int:
    """Whole bytes holding ``bits`` — the second ceiling students forget."""
    return -(-bits // 8)


def is_power_of_two(n: int) -> bool:
    return n > 0 and n & (n - 1) == 0


def count_digit(text: str, digit: str) -> int:
    return text.count(digit)


def parity_bit(bits: str, even: bool = True) -> str:
    """Parity bit appended by the task-5 algorithms."""
    ones = bits.count("1")
    if even:
        return "0" if ones % 2 == 0 else "1"
    return "1" if ones % 2 == 0 else "0"


def unique_extremum(values: Iterable[int], *, largest: bool) -> int | None:
    """The extremum of ``values``, or ``None`` when it is not attained uniquely.

    Generators call this to refuse instances whose "smallest/largest A" answer is
    ambiguous (doc 7.1.2).
    """
    items = list(values)
    if not items:
        return None
    target = max(items) if largest else min(items)
    return target if items.count(target) == 1 else None


def sole(values: Sequence[int]) -> int | None:
    """The single element of ``values``, or ``None`` when there is not exactly one."""
    return values[0] if len(values) == 1 else None
