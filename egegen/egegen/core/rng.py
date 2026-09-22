"""Deterministic randomness.

Every generator draws exclusively from a :class:`Rng` built from the instance seed,
so a seed fully determines the instance. Using ``random.Random`` directly (module
level) would leak global state between generators and break that guarantee.
"""

from __future__ import annotations

import random
from collections.abc import Sequence
from typing import TypeVar

T = TypeVar("T")


class Rng:
    """Thin, explicit wrapper over :class:`random.Random`."""

    __slots__ = ("_r", "seed")

    def __init__(self, seed: int) -> None:
        self.seed = seed
        self._r = random.Random(seed)

    def fork(self, tag: str) -> Rng:
        """An independent stream derived from this one, stable per tag.

        Lets a generator draw the statement and the dataset from separate streams so
        that changing one does not shift the other.
        """
        return Rng((self.seed * 1_000_003 + _tag_hash(tag)) & 0x7FFF_FFFF_FFFF_FFFF)

    def randint(self, a: int, b: int) -> int:
        return self._r.randint(a, b)

    def choice(self, seq: Sequence[T]) -> T:
        return self._r.choice(seq)

    def choices(self, seq: Sequence[T], k: int) -> list[T]:
        return self._r.choices(list(seq), k=k)

    def sample(self, seq: Sequence[T], k: int) -> list[T]:
        return self._r.sample(list(seq), k)

    def shuffle(self, items: list[T]) -> None:
        self._r.shuffle(items)

    def random(self) -> float:
        return self._r.random()

    def chance(self, p: float) -> bool:
        return self._r.random() < p

    def permutation(self, n: int) -> list[int]:
        items = list(range(n))
        self._r.shuffle(items)
        return items


def _tag_hash(tag: str) -> int:
    h = 1469598103934665603
    for byte in tag.encode():
        h = ((h ^ byte) * 1099511628211) & 0xFFFF_FFFF_FFFF_FFFF
    return h


def bulk_ints(seed: int, count: int, lo: int, hi: int) -> list[int]:
    """``count`` deterministic integers in ``[lo, hi]``, generated in bulk.

    Drawing a million numbers one ``randint`` at a time costs seconds; pulling the
    entropy as one block of bytes and reinterpreting it as 32-bit words is two orders
    of magnitude faster and just as reproducible.
    """
    import array

    if count < 0:
        raise ValueError("count must be non-negative")
    span = hi - lo + 1
    if span <= 0:
        raise ValueError("empty range")
    words = array.array("I")
    if words.itemsize != 4:  # pragma: no cover - every mainstream platform is 4
        words = array.array("L")
    raw = random.Random(seed).randbytes(words.itemsize * count)
    words.frombytes(raw)
    return [lo + (value % span) for value in words]
