"""Shared engine for tasks 19-21.

The exam asks three questions about one game, and the design doc's template answers
all three with the predicates W1/L1/W2/L2. This module holds the game catalogue and
the statement wording; ``t19``/``t20``/``t21`` differ only in which predicate they
query and how many values they expect.
"""

from __future__ import annotations

from typing import Any

from egegen.core.rng import Rng
from egegen.solvers.games import (
    GameAnalyzer,
    MoveFn,
    State,
    best_win_depth,
    decreasing_moves,
    one_pile_moves,
    two_pile_moves,
)

SUBTYPES = (
    "g1_add_double",
    "g2_add_k_times_k",
    "g3_two_piles",
    "g5_three_moves",
    "g6_decreasing",
)


def spec_candidates(rng: Rng, subtype: str, difficulty: int) -> list[dict[str, Any]]:
    """Every game of this subtype worth trying, in a seed-dependent order.

    A task asks for a specific shape of answer — exactly two values for task 20, at
    least one for 19 and 21 — and not every game has it. Returning a list lets the
    generator walk candidates deterministically instead of re-rolling at random.
    """
    match subtype:
        case "g1_add_double":
            targets = [55, 65, 73, 85, 97, 111, 129, 145, 161, 193, 225, 257]
            base: list[dict[str, Any]] = [
                {"kind": "one_pile", "adds": [1], "muls": [2], "target": t} for t in targets
            ]
        case "g2_add_k_times_k":
            targets = [61, 71, 81, 91, 101, 111, 121, 145, 161, 175, 201, 241]
            base = [
                {"kind": "one_pile", "adds": [add], "muls": [mul], "target": t}
                for add, mul in ((2, 2), (3, 3), (4, 4), (1, 3), (2, 3), (1, 4), (3, 2))
                for t in targets
            ]
        case "g3_two_piles":
            base = [
                {
                    "kind": "two_piles",
                    "adds": [1],
                    "muls": [2],
                    "fixed": fixed,
                    "target": t,
                }
                for fixed in range(4, 21)
                for t in (41, 49, 55, 59, 65, 69, 77, 85)
            ]
        case "g5_three_moves":
            base = [
                {"kind": "one_pile", "adds": adds, "muls": [2], "target": t}
                for adds in ([1, 2], [1, 3], [2, 3])
                for t in (41, 49, 55, 61, 67, 73, 81, 89, 101)
            ]
        case "g6_decreasing":
            base = [
                {"kind": "decreasing", "subs": subs, "target": t}
                for subs in ([1, 2], [1, 3], [2, 3], [1, 2, 3])
                for t in range(19, 60, 2)
            ]
        case _:
            raise ValueError(subtype)
    # Harder instances use larger targets; easier ones stay small and countable.
    base.sort(key=lambda spec: spec["target"], reverse=difficulty >= 4)
    head = base[: max(8, len(base) // 2)]
    rng.shuffle(head)
    return head + base[len(head) :]


def spec_for(rng: Rng, subtype: str, difficulty: int) -> dict[str, Any]:
    return spec_candidates(rng, subtype, difficulty)[0]


def analyzer_for(spec: dict[str, Any]) -> tuple[GameAnalyzer, MoveFn, Any, list[State]]:
    """Build the analyser, the move function, the end test and the states to scan."""
    target = spec["target"]
    match spec["kind"]:
        case "one_pile":
            moves = one_pile_moves(spec["adds"], spec["muls"])

            def final_one(s: State) -> bool:
                assert isinstance(s, int)
                return s >= target

            states: list[State] = list(range(1, target))
            return GameAnalyzer(moves, final_one), moves, final_one, states
        case "two_piles":
            moves = two_pile_moves(spec["adds"], spec["muls"])
            fixed = spec["fixed"]

            def final_two(s: State) -> bool:
                assert isinstance(s, tuple)
                return s[0] + s[1] >= target

            states = [(fixed, k) for k in range(1, target - fixed)]
            return GameAnalyzer(moves, final_two), moves, final_two, states
        case "decreasing":
            moves = decreasing_moves(spec["subs"])

            def final_dec(s: State) -> bool:
                assert isinstance(s, int)
                return s == 0

            states = list(range(1, target + 1))
            return GameAnalyzer(moves, final_dec), moves, final_dec, states
    raise ValueError(spec["kind"])


def state_value(state: State, spec: dict[str, Any]) -> int:
    """The number the student actually writes down for this state."""
    if spec["kind"] == "two_piles":
        assert isinstance(state, tuple)
        return state[1]
    assert isinstance(state, int)
    return state


def scan(spec: dict[str, Any], predicate: str) -> list[int]:
    """Values of S satisfying one of W1/L1/W2/L2, in increasing order."""
    analyzer, _, _, states = analyzer_for(spec)
    return sorted(
        state_value(s, spec) for s in analyzer.scan(states, predicate)
    )


def scan_naive(spec: dict[str, Any], predicate: str) -> list[int]:
    """Same scan via plain iterative-deepening minimax, sharing no memo table."""
    _, moves, is_final, states = analyzer_for(spec)

    def depth(s: State) -> int | None:
        return best_win_depth(s, moves, is_final, 3)

    out: list[int] = []
    for s in states:
        options = moves(s)
        if not options:
            continue
        own = depth(s)
        replies = [depth(m) for m in options]
        match predicate:
            case "W1":
                ok = own == 1
            case "L1":
                ok = own != 1 and all(d == 1 for d in replies)
            case "W2":
                ok = own == 2
            case "L2":
                ok = (
                    own != 1
                    and not all(d == 1 for d in replies)
                    and all(d is not None and d <= 2 for d in replies)
                )
            case _:
                raise ValueError(predicate)
        if ok:
            out.append(state_value(s, spec))
    return sorted(out)


def describe_moves(spec: dict[str, Any]) -> str:
    match spec["kind"]:
        case "one_pile":
            parts = [f"добавить в кучу {k} " + _stones(k) for k in spec["adds"]]
            parts += [
                "увеличить количество камней в куче в " + _times(k) for k in spec["muls"]
            ]
            return "; ".join(parts)
        case "two_piles":
            parts = [f"добавить {k} " + _stones(k) + " в одну из куч" for k in spec["adds"]]
            parts += [
                "увеличить количество камней в одной из куч в " + _times(k)
                for k in spec["muls"]
            ]
            return "; ".join(parts)
        case "decreasing":
            return "; ".join(f"убрать из кучи {k} " + _stones(k) for k in spec["subs"])
    raise ValueError(spec["kind"])


def describe_end(spec: dict[str, Any]) -> str:
    target = spec["target"]
    if spec["kind"] == "decreasing":
        return (
            "Игра завершается, когда в куче не остаётся камней. Выигрывает игрок, "
            "сделавший последний ход (то есть забравший последние камни)."
        )
    where = "в куче" if spec["kind"] == "one_pile" else "в двух кучах суммарно"
    return (
        f"Игра завершается в тот момент, когда количество камней {where} "
        f"становится не менее **{target}**. Выигрывает игрок, сделавший последний "
        "ход, то есть первым получивший такую позицию."
    )


def describe_start(spec: dict[str, Any]) -> str:
    if spec["kind"] == "two_piles":
        return (
            f"В первой куче {spec['fixed']} " + _stones(spec["fixed"]) + ", "
            "во второй — S камней; S — целое число, большее нуля."
        )
    if spec["kind"] == "decreasing":
        return "В куче S камней; S — целое число, большее нуля."
    return "В начале игры в куче S камней; S — целое число, большее нуля."


def _stones(k: int) -> str:
    if k % 10 == 1 and k % 100 != 11:
        return "камень"
    if k % 10 in (2, 3, 4) and k % 100 not in (12, 13, 14):
        return "камня"
    return "камней"


def _times(k: int) -> str:
    return {2: "два раза", 3: "три раза", 4: "четыре раза"}.get(k, f"{k} раз")
