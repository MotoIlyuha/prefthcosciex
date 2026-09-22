"""Golden values quoted in the design doc, as executable assertions.

If any of these drift, a generator has changed meaning — not just its wording.
"""

from __future__ import annotations

import pytest

from egegen.solvers.executor import (
    count_avoiding,
    count_programs,
    count_programs_naive,
    count_through,
)
from egegen.solvers.games import GameAnalyzer, one_pile_moves
from egegen.solvers.graphs import (
    all_simple_paths,
    count_paths_dag,
    count_paths_dag_avoiding,
    count_paths_dag_through,
    dijkstra,
    floyd_warshall,
)
from egegen.solvers.numbers import bits_per_symbol, bytes_for_bits, to_base
from egegen.solvers.polygon import (
    count_lattice_points,
    rectangle_formula,
    turtle_polygon,
)


def test_games_n129_matches_design_doc() -> None:
    """Appendix B: N = 129 with moves +1 and x2 gives 19 -> 64, 20 -> 32 & 63, 21 -> 62."""
    n = 129
    game = GameAnalyzer(one_pile_moves([1], [2]), lambda s: s >= n)
    assert [s for s in range(1, n) if game.L1(s)] == [64]
    assert [s for s in range(1, n) if game.W2(s)] == [32, 63]
    assert [s for s in range(1, n) if game.L2(s)] == [62]


def test_turtle_rectangle_matches_formula() -> None:
    """Appendix B task 6: a 12x8 rectangle, strictly inside and with the border."""
    poly = turtle_polygon([(12, -90), (8, -90)] * 2)
    assert count_lattice_points(poly, strict=True) == rectangle_formula(12, 8, strict=True)
    assert count_lattice_points(poly, strict=False) == rectangle_formula(
        12, 8, strict=False
    )
    assert count_lattice_points(poly, strict=True) == 77


def test_executor_counts_match_appendix_b() -> None:
    """Appendix B task 13: commands +1 and x2."""
    commands = ["add1", "mul2"]
    assert count_programs(3, 12, commands) == count_programs_naive(3, 12, commands)
    assert count_through(3, 12, 20, commands) == count_programs(3, 12, commands) * (
        count_programs(12, 20, commands)
    )
    assert count_avoiding(3, 20, 15, commands) == count_programs(
        3, 20, commands
    ) - count_through(3, 15, 20, commands)
    # The empty program counts: f(x, x) = 1.
    assert count_programs(7, 7, commands) == 1


def test_dag_path_counts_match_appendix_b() -> None:
    """Appendix B task 23: A->E is 3 paths, 2 through B, 1 avoiding B."""
    dag = {"A": ["B", "C"], "B": ["D"], "C": ["B", "D"], "D": ["E"], "E": []}
    assert count_paths_dag(dag, "A", "E") == 3
    assert count_paths_dag_through(dag, "A", "B", "E") == 2
    assert count_paths_dag_avoiding(dag, "A", "E", "B") == 1
    assert len(all_simple_paths(dag, "A", "E")) == 3


def test_dijkstra_agrees_with_floyd() -> None:
    graph = {
        "A": {"B": 3, "C": 1},
        "B": {"A": 3, "D": 1},
        "C": {"A": 1, "D": 5},
        "D": {"B": 1, "C": 5},
    }
    floyd = floyd_warshall(graph)
    for source in graph:
        assert dijkstra(graph, source) == {k: v for k, v in floyd[source].items()}


@pytest.mark.parametrize(
    ("value", "base", "expected"),
    [(0, 2, "0"), (5, 2, "101"), (255, 16, "FF"), (35, 36, "Z"), (10, 3, "101")],
)
def test_to_base(value: int, base: int, expected: str) -> None:
    assert to_base(value, base) == expected


def test_appendix_a_task_14_example() -> None:
    """Appendix B: zeros in the base-9 representation of 3**150 + 5**40 - 17."""
    assert to_base(3**150 + 5**40 - 17, 9).count("0") == 46


@pytest.mark.parametrize(
    ("alphabet", "bits"), [(2, 1), (10, 4), (26, 5), (32, 5), (33, 6), (62, 6), (64, 6)]
)
def test_bits_per_symbol(alphabet: int, bits: int) -> None:
    assert bits_per_symbol(alphabet) == bits


def test_bytes_for_bits_rounds_up() -> None:
    assert bytes_for_bits(1) == 1
    assert bytes_for_bits(8) == 1
    assert bytes_for_bits(9) == 2
    assert bytes_for_bits(70) == 9
