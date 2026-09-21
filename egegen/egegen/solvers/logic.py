"""Boolean formula AST used by tasks 2 (truth tables) and 15 (logic with a parameter)."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from itertools import permutations, product

# Operator precedence as taught for the exam: ¬, ∧, ∨, →, ≡
PRECEDENCE = {"not": 4, "and": 3, "or": 2, "impl": 1, "equiv": 0, "xor": 0}
SYMBOL = {"not": "¬", "and": "∧", "or": "∨", "impl": "→", "equiv": "≡", "xor": "⊕"}
PY_SYMBOL = {"and": "and", "or": "or", "impl": "<=", "equiv": "==", "xor": "!="}


@dataclass(frozen=True, slots=True)
class Node:
    """A formula node: a variable leaf, a negation, or a binary connective."""

    op: str
    left: Node | None = None
    right: Node | None = None
    var: str = ""

    def evaluate(self, env: Mapping[str, bool]) -> bool:
        if self.op == "var":
            return env[self.var]
        assert self.left is not None
        if self.op == "not":
            return not self.left.evaluate(env)
        assert self.right is not None
        a, b = self.left.evaluate(env), self.right.evaluate(env)
        match self.op:
            case "and":
                return a and b
            case "or":
                return a or b
            case "impl":
                return (not a) or b
            case "equiv":
                return a == b
            case "xor":
                return a != b
        raise ValueError(f"unknown operator {self.op!r}")

    def variables(self) -> list[str]:
        if self.op == "var":
            return [self.var]
        out = list(self.left.variables()) if self.left else []
        if self.right:
            for v in self.right.variables():
                if v not in out:
                    out.append(v)
        return out

    def to_text(self, parent_prec: int = -1) -> str:
        """Render with the minimum parentheses the exam's precedence rules require."""
        if self.op == "var":
            return self.var
        if self.op == "not":
            assert self.left is not None
            inner = self.left.to_text(PRECEDENCE["not"])
            return f"¬{inner}"
        assert self.left is not None and self.right is not None
        prec = PRECEDENCE[self.op]
        text = f"{self.left.to_text(prec)} {SYMBOL[self.op]} {self.right.to_text(prec + 1)}"
        return f"({text})" if prec < parent_prec else text

    def to_python(self, parent_prec: int = -1) -> str:
        if self.op == "var":
            return self.var
        if self.op == "not":
            assert self.left is not None
            return f"not {self.left.to_python(PRECEDENCE['not'])}"
        assert self.left is not None and self.right is not None
        prec = PRECEDENCE[self.op]
        text = (
            f"{self.left.to_python(prec)} {PY_SYMBOL[self.op]} "
            f"{self.right.to_python(prec + 1)}"
        )
        return f"({text})" if prec < parent_prec else text


def var(name: str) -> Node:
    return Node("var", var=name)


def not_(node: Node) -> Node:
    return Node("not", node)


def binary(op: str, left: Node, right: Node) -> Node:
    return Node(op, left, right)


def satisfying_sets(
    formula: Node, variables: Sequence[str], value: bool
) -> list[tuple[int, ...]]:
    """All variable assignments where the formula equals ``value``."""
    out: list[tuple[int, ...]] = []
    for combo in product([0, 1], repeat=len(variables)):
        env = {v: bool(b) for v, b in zip(variables, combo, strict=True)}
        if formula.evaluate(env) is value:
            out.append(combo)
    return out


Row = tuple[int | None, ...]


def column_orders(
    formula: Node,
    variables: Sequence[str],
    rows: Sequence[Row],
    value: bool,
) -> list[str]:
    """Every column ordering consistent with the partially filled table.

    A permutation ``p`` means "column j holds variable ``variables[p[j]]``". Distinct
    rows must map to distinct satisfying assignments (a table never repeats a row).
    """
    sets = satisfying_sets(formula, variables, value)
    found: list[str] = []
    n = len(variables)
    for p in permutations(range(n)):
        if _order_fits(rows, sets, p, n):
            found.append("".join(variables[i] for i in p))
    return found


def _order_fits(
    rows: Sequence[Row], sets: Sequence[tuple[int, ...]], p: tuple[int, ...], n: int
) -> bool:
    """True when each row can be matched to a distinct satisfying assignment."""
    candidates: list[list[int]] = []
    for row in rows:
        matches = [
            idx
            for idx, s in enumerate(sets)
            if all(row[j] is None or row[j] == s[p[j]] for j in range(n))
        ]
        if not matches:
            return False
        candidates.append(matches)
    return _has_distinct_assignment(candidates)


def _has_distinct_assignment(candidates: Sequence[Sequence[int]]) -> bool:
    """Bipartite matching (Kuhn) — rows to satisfying assignments, all distinct."""
    match: dict[int, int] = {}

    def try_assign(row: int, seen: set[int]) -> bool:
        for c in candidates[row]:
            if c in seen:
                continue
            seen.add(c)
            if c not in match or try_assign(match[c], seen):
                match[c] = row
                return True
        return False

    return all(try_assign(r, set()) for r in range(len(candidates)))


def holds_for_all(predicate: Callable[[int], bool], domain: Sequence[int]) -> bool:
    return all(predicate(x) for x in domain)
