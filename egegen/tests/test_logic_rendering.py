"""A formula's Python rendering must mean exactly what the formula means.

Minimal parentheses are unsafe here: ``not`` binds looser than the comparison
operators standing in for -> and ==, and Python chains comparisons. The rendered
source is handed to students, so a mismatch would teach the wrong thing.
"""

from __future__ import annotations

from itertools import product

from egegen.core.rng import Rng
from egegen.solvers.logic import Node, binary, not_, var

OPS = ["and", "or", "impl", "equiv", "xor"]
NAMES = ["x", "y", "z", "w"]


def _random_formula(rng: Rng, depth: int) -> Node:
    if depth == 0:
        return var(rng.choice(NAMES))
    if rng.chance(0.2):
        return not_(_random_formula(rng, depth - 1))
    return binary(
        rng.choice(OPS), _random_formula(rng, depth - 1), _random_formula(rng, depth - 1)
    )


def test_python_rendering_matches_ast_evaluation() -> None:
    for seed in range(300):
        rng = Rng(seed)
        formula = _random_formula(rng, 3)
        source = formula.to_python()
        compiled = eval(f"lambda x, y, z, w: {source}")  # noqa: S307 - our own source
        for combo in product([False, True], repeat=4):
            env = dict(zip(NAMES, combo, strict=True))
            assert formula.evaluate(env) == compiled(**env), (
                f"seed={seed} formula={formula.to_text()} python={source} env={env}"
            )


def test_rendering_is_fully_parenthesised() -> None:
    formula = binary("xor", not_(var("w")), binary("impl", var("y"), not_(var("x"))))
    assert formula.to_python() == "(not w) != (y <= (not x))"
    assert formula.to_text() == "¬w ⊕ (y → ¬x)"
