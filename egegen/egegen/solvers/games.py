"""Game analysis for tasks 19-21 (design doc, Appendix A and B).

The exam's three game questions are one algorithm with three queries:

* 19 -> ``L1``: the mover cannot win in one move, and every move he has lets the
  opponent win immediately.
* 20 -> ``W2``: the mover cannot win in one move, but has a move into ``L1``.
* 21 -> ``L2``: the mover can win neither in one move nor by the ``L1`` pattern, and
  every move he has leaves the opponent able to win in one or two.

Self-check from the doc: N = 129 with moves {+1, x2} gives 19 -> 64, 20 -> 32 and 63,
21 -> 62.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from functools import lru_cache
from typing import TypeAlias

State: TypeAlias = int | tuple[int, ...]
MoveFn: TypeAlias = Callable[[State], list[State]]


class GameAnalyzer:
    """Win/loss classification of a stone game with a target threshold.

    ``moves`` maps a state to its successors; ``is_final`` decides whether the state
    that has just been reached ends the game (the player who reached it wins, unless
    ``misere`` is set).
    """

    def __init__(
        self,
        moves: MoveFn,
        is_final: Callable[[State], bool],
        *,
        misere: bool = False,
    ) -> None:
        self._moves = moves
        self._is_final = is_final
        self.misere = misere
        self.W1 = lru_cache(maxsize=None)(self._w1)
        self.L1 = lru_cache(maxsize=None)(self._l1)
        self.W2 = lru_cache(maxsize=None)(self._w2)
        self.L2 = lru_cache(maxsize=None)(self._l2)

    def legal_moves(self, s: State) -> list[State]:
        return self._moves(s)

    def _wins_now(self, s: State) -> bool:
        """True if reaching ``s`` ends the game in favour of whoever reached it."""
        return self._is_final(s) != self.misere

    def _w1(self, s: State) -> bool:
        return any(self._wins_now(m) for m in self._moves(s))

    def _l1(self, s: State) -> bool:
        ms = self._moves(s)
        return bool(ms) and not self.W1(s) and all(self.W1(m) for m in ms)

    def _w2(self, s: State) -> bool:
        return not self.W1(s) and any(self.L1(m) for m in self._moves(s))

    def _l2(self, s: State) -> bool:
        ms = self._moves(s)
        return (
            bool(ms)
            and not self.W1(s)
            and not self.L1(s)
            and all(self.W1(m) or self.W2(m) for m in ms)
        )

    def scan(self, states: Iterable[State], predicate: str) -> list[State]:
        fn = {"W1": self.W1, "L1": self.L1, "W2": self.W2, "L2": self.L2}[predicate]
        return [s for s in states if fn(s)]


def one_pile_moves(adds: Sequence[int], muls: Sequence[int]) -> MoveFn:
    """Moves for a single pile: add each of ``adds``, multiply by each of ``muls``."""

    def moves(s: State) -> list[State]:
        assert isinstance(s, int)
        return [s + a for a in adds] + [s * m for m in muls]

    return moves


def two_pile_moves(adds: Sequence[int], muls: Sequence[int]) -> MoveFn:
    """Moves for two piles: apply each operation to either pile."""

    def moves(s: State) -> list[State]:
        assert isinstance(s, tuple)
        a, b = s
        out: list[tuple[int, int]] = []
        out += [(a + k, b) for k in adds] + [(a, b + k) for k in adds]
        out += [(a * k, b) for k in muls] + [(a, b * k) for k in muls]
        return list(out)

    return moves


def decreasing_moves(subs: Sequence[int]) -> MoveFn:
    """Moves for a 'remove stones' game; moves that would go below zero are dropped."""

    def moves(s: State) -> list[State]:
        assert isinstance(s, int)
        return [s - k for k in subs if s - k >= 0]

    return moves


def naive_outcome(
    state: State,
    moves: MoveFn,
    is_final: Callable[[State], bool],
    depth: int,
    *,
    misere: bool = False,
) -> bool | None:
    """Plain minimax to ``depth`` plies — the independent cross-check of the analyser.

    Returns True when the player to move wins within ``depth`` moves, False when the
    opponent does, and ``None`` when the game is still undecided at that horizon.
    """
    if depth <= 0:
        return None
    results: list[bool | None] = []
    for m in moves(state):
        if is_final(m):
            results.append(True if not misere else False)
            continue
        sub = naive_outcome(m, moves, is_final, depth - 1, misere=misere)
        results.append(None if sub is None else not sub)
    if not results:
        return False if not misere else True
    if any(r is True for r in results):
        return True
    if all(r is False for r in results):
        return False
    return None
