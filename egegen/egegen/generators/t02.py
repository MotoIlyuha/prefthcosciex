"""Task 2 — recovering the column order of a truth table.

A logical function is given; a fragment of its truth table is shown with the columns
labelled only "Перем. 1 … Перем. 4". The answer is the variable order. An instance is
released only when exactly one permutation fits, which is checked by enumeration.
"""

from __future__ import annotations

from typing import Any

from egegen.core.errors import GenerationFailedError
from egegen.core.generator import Generator
from egegen.core.registry import register
from egegen.core.rng import Rng
from egegen.core.templates import render
from egegen.core.types import Instance, Uniqueness
from egegen.generators._common import markdown_table
from egegen.solvers.logic import (
    Node,
    binary,
    column_orders,
    column_orders_with_pools,
    not_,
    satisfying_sets,
    var,
)

BINARY_OPS = ["and", "or", "impl", "equiv", "xor"]
VARIABLE_NAMES = ["x", "y", "z", "w"]


class Task02(Generator):
    task_no = 2
    answer_kind = "letters"
    checker = "letters"
    uniqueness = Uniqueness.ENUMERATED

    def build(self, rng: Rng, difficulty: int, subtype: str) -> Instance:
        for _ in range(80):
            candidate = self._attempt(rng, difficulty, subtype)
            if candidate is not None:
                return candidate
            rng = rng.fork("retry")
        raise GenerationFailedError(f"t02/{subtype}: no instance with a unique column order")

    def _attempt(self, rng: Rng, difficulty: int, subtype: str) -> Instance | None:
        n_vars = 3 if subtype == "2.3_three_vars" else 4
        variables = VARIABLE_NAMES[:n_vars]
        depth = 2 if difficulty <= 2 else (3 if difficulty <= 4 else 4)
        formula = self._random_formula(rng.fork("formula"), variables, depth)
        if sorted(set(formula.variables())) != sorted(variables):
            return None  # every variable must actually appear, or columns are ambiguous
        if self._has_symmetric_pair(formula, variables):
            # Swapping two variables leaves the function unchanged, so at least two
            # column orders always fit and the task has no single answer.
            return None

        n_rows = 3 if difficulty <= 3 else 4
        mixed = subtype == "2.5_mixed_values"
        value = subtype != "2.4_value_one"  # 2.4 pins F = 1, others use F = 0
        values = [rng.chance(0.5) for _ in range(n_rows)] if mixed else [value] * n_rows

        # Rather than draw rows at random and hope the column order is pinned down,
        # build the table greedily: at each step add the row that rules out the most
        # wrong permutations, and stop as soon as exactly one survives.
        pools = {v: satisfying_sets(formula, variables, v) for v in (True, False)}
        for v in set(values):
            if len(pools[v]) < n_rows:
                return None

        perm = tuple(rng.permutation(n_vars))
        answer = "".join(variables[i] for i in perm)
        target_blanks = self._blank_count(subtype, difficulty, n_rows, n_vars)
        blank_plan = self._blank_plan(rng.fork("blanks"), target_blanks, n_rows, n_vars)

        # Try with the planned blanks first; if no table pins the order down, fall
        # back to a fully filled one rather than discarding a perfectly good formula.
        built = None
        for plan in (blank_plan, {}):
            built = self._build_table(rng, pools, variables, perm, answer, values, n_rows, plan)
            if built is not None:
                break
        if built is None:
            return None
        rows, values = built
        n_rows = len(rows)

        meta: dict[str, Any] = {
            "subtype": subtype,
            "variables": variables,
            "formula_text": formula.to_text(),
            "formula_python": formula.to_python(),
            "formula": _serialise(formula),
            "rows": [list(r) for r in rows],
            "values": [int(v) for v in values],
        }
        table = markdown_table(
            [f"Перем. {j + 1}" for j in range(n_vars)] + ["F"],
            [[*row, int(v)] for row, v in zip(rows, values, strict=True)],
        )
        template = self.templates.pick(rng, subtype)
        return Instance(
            task_no=self.task_no,
            subtype=subtype,
            difficulty=difficulty,
            seed=0,
            statement_md=render(
                template,
                formula=formula.to_text(),
                table=table,
                variables=", ".join(variables),
                n=n_vars,
            ),
            answer=answer,
            checker_options={"alphabet": "".join(variables), "length": n_vars},
            solution_steps=self._solution(meta, answer),
            template_id=template.id,
            meta=meta,
        )

    def _build_table(
        self,
        rng: Rng,
        pools: dict[bool, list[tuple[int, ...]]],
        variables: list[str],
        perm: tuple[int, ...],
        answer: str,
        values: list[bool],
        n_rows: int,
        blank_plan: dict[int, tuple[int, ...]],
    ) -> tuple[list[list[int | None]], list[bool]] | None:
        """Grow the table row by row, each time adding the row that rules out the
        most wrong column orders, stopping as soon as exactly one survives."""
        n_vars = len(variables)
        rows: list[list[int | None]] = []
        row_values: list[bool] = []
        used: set[tuple[int, ...]] = set()
        # A non-symmetric function is always pinned down by enough rows; cap the
        # table at six so it still looks like an exam fragment.
        max_rows = min(6, max(len(pools[v]) for v in set(values)))

        for step in range(max_rows):
            value = values[step] if step < len(values) else values[-1]
            pool = [s for s in pools[value] if s not in used]
            if not pool:
                return None
            best: tuple[int, list[int | None], tuple[int, ...]] | None = None
            # Eight candidates is plenty to find a row that cuts the survivor set;
            # scanning the whole pool at every step would dominate generation time.
            for candidate_set in pool if len(pool) <= 8 else rng.sample(pool, 8):
                row: list[int | None] = [candidate_set[perm[j]] for j in range(n_vars)]
                for column in blank_plan.get(step, ()):
                    row[column] = None
                survivors = column_orders_with_pools(
                    pools,
                    variables,
                    [tuple(r) for r in [*rows, row]],
                    [*row_values, value],
                )
                if answer not in survivors:
                    continue  # blanking made the intended order inconsistent
                if best is None or len(survivors) < best[0]:
                    best = (len(survivors), row, candidate_set)
            if best is None:
                return None
            _, row, candidate_set = best
            rows.append(row)
            row_values.append(value)
            used.add(candidate_set)
            if step + 1 >= n_rows and best[0] == 1:
                return rows, row_values
        return None

    def _blank_plan(
        self, rng: Rng, blanks: int, rows: int, cols: int
    ) -> dict[int, tuple[int, ...]]:
        """Which cells to leave empty, decided up front so the greedy build is stable."""
        cells = [(r, c) for r in range(rows + 2) for c in range(cols)]
        rng.shuffle(cells)
        plan: dict[int, list[int]] = {}
        for r, c in cells[:blanks]:
            plan.setdefault(r, []).append(c)
        return {r: tuple(sorted(cs)) for r, cs in plan.items() if len(cs) < cols}

    def _blank_count(self, subtype: str, difficulty: int, rows: int, cols: int) -> int:
        if subtype == "2.1_full_rows":
            return 0
        budget = {2: 1, 3: 2, 4: 3, 5: 4}.get(difficulty, 2)
        return min(budget, rows * cols - rows)

    def _has_symmetric_pair(self, formula: Node, variables: list[str]) -> bool:
        """True if swapping some two variables leaves the truth table unchanged."""
        from itertools import product

        n = len(variables)
        table = {
            combo: formula.evaluate(dict(zip(variables, map(bool, combo), strict=True)))
            for combo in product([0, 1], repeat=n)
        }
        for i in range(n):
            for j in range(i + 1, n):
                if all(table[combo] == table[_swap(combo, i, j)] for combo in table):
                    return True
        return False

    def _random_formula(self, rng: Rng, variables: list[str], depth: int) -> Node:
        """Build a formula from the exam's grammar, keeping every variable present."""
        pool: list[Node] = [var(v) for v in variables]
        rng.shuffle(pool)
        while len(pool) > 1:
            left = pool.pop()
            right = pool.pop()
            if rng.chance(0.35):
                left = not_(left)
            if rng.chance(0.25):
                right = not_(right)
            pool.append(binary(rng.choice(BINARY_OPS), left, right))
            rng.shuffle(pool)
        node = pool[0]
        for _ in range(max(0, depth - 3)):
            if rng.chance(0.5):
                node = not_(node)
            else:
                node = binary(rng.choice(BINARY_OPS), node, var(rng.choice(variables)))
        return node

    # -- solving ------------------------------------------------------------
    def solve_fast(self, meta: dict[str, Any]) -> str:
        """Bipartite matching of rows to satisfying assignments, per permutation."""
        formula = _deserialise(meta["formula"])
        orders = column_orders(
            formula,
            meta["variables"],
            [tuple(r) for r in meta["rows"]],
            [bool(v) for v in meta["values"]],
        )
        if len(orders) != 1:
            raise GenerationFailedError(f"t02: column order is not unique: {orders}")
        return orders[0]

    def solve_naive(self, meta: dict[str, Any]) -> str | None:
        """Plain backtracking instead of bipartite matching.

        For each of the 6 or 24 column orders, collect every row's candidate
        assignments and then hand out distinct ones by depth-first search with undo,
        most constrained row first. This is the textbook approach the doc's template
        spells out; it shares no code with the Kuhn matching in :meth:`solve_fast`.
        """
        from itertools import permutations

        formula = _deserialise(meta["formula"])
        variables: list[str] = meta["variables"]
        n = len(variables)
        rows = [tuple(r) for r in meta["rows"]]
        values = [bool(v) for v in meta["values"]]
        pools = {v: satisfying_sets(formula, variables, v) for v in set(values)}

        def fits(p: tuple[int, ...]) -> bool:
            per_row = [
                [
                    s
                    for s in pools[values[i]]
                    if all(rows[i][j] is None or rows[i][j] == s[p[j]] for j in range(n))
                ]
                for i in range(len(rows))
            ]
            if any(not options for options in per_row):
                return False
            order = sorted(range(len(rows)), key=lambda i: len(per_row[i]))
            used: set[tuple[int, ...]] = set()

            def place(k: int) -> bool:
                if k == len(order):
                    return True
                for s in per_row[order[k]]:
                    if s in used:
                        continue
                    used.add(s)
                    if place(k + 1):
                        return True
                    used.discard(s)
                return False

            return place(0)

        found = ["".join(variables[i] for i in p) for p in permutations(range(n)) if fits(p)]
        return found[0] if len(found) == 1 else None

    def enumerate_answers(self, meta: dict[str, Any]) -> list[str] | None:
        formula = _deserialise(meta["formula"])
        return sorted(
            column_orders(
                formula,
                meta["variables"],
                [tuple(r) for r in meta["rows"]],
                [bool(v) for v in meta["values"]],
            )
        )

    # -- explanation --------------------------------------------------------
    def _solution(self, meta: dict[str, Any], answer: str) -> list[str]:
        variables = meta["variables"]
        formula = _deserialise(meta["formula"])
        values = [bool(v) for v in meta["values"]]
        counts = {v: len(satisfying_sets(formula, variables, v)) for v in set(values)}
        counts_text = ", ".join(
            f"F = {int(v)} на {counts[v]} наборах" for v in sorted(counts, key=int)
        )
        return [
            "**Шаг 1.** Запишем функцию на Python. Импликация `→` — это `<=`, "
            "эквивалентность `≡` — это `==`, исключающее «или» `⊕` — это `!=`:\n\n"
            f"```python\ndef F({', '.join(variables)}):\n"
            f"    return {formula.to_python()}\n```",
            f"**Шаг 2.** Переберём все {2 ** len(variables)} наборов переменных и "
            f"оставим подходящие по значению F: {counts_text}.",
            f"**Шаг 3.** Переберём {'6' if len(variables) == 3 else '24'} перестановки "
            "столбцов. Для каждой проверим, что каждую строку таблицы можно "
            "сопоставить **своему** набору (две строки не могут отвечать одному "
            "набору), а пустая ячейка подходит под любое значение.",
            f"**Шаг 4.** Подходит ровно одна перестановка: **{answer}**. Если бы "
            "печаталось больше одной — значит, функция записана неверно.",
        ]


def _swap(combo: tuple[int, ...], i: int, j: int) -> tuple[int, ...]:
    out = list(combo)
    out[i], out[j] = out[j], out[i]
    return tuple(out)


def _serialise(node: Node) -> dict[str, Any]:
    """AST -> plain dict, because ``Instance.meta`` is stored as jsonb."""
    if node.op == "var":
        return {"op": "var", "var": node.var}
    out: dict[str, Any] = {"op": node.op, "left": _serialise(node.left)}  # type: ignore[arg-type]
    if node.right is not None:
        out["right"] = _serialise(node.right)
    return out


def _deserialise(data: dict[str, Any]) -> Node:
    if data["op"] == "var":
        return var(data["var"])
    left = _deserialise(data["left"])
    if "right" not in data:
        return not_(left)
    return binary(data["op"], left, _deserialise(data["right"]))


register(Task02())
