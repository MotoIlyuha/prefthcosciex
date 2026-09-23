"""Task 15 — find the extreme parameter A making a formula identically true.

"Identically true" means: not a single counterexample over the whole domain. Each
subtype has a structural shortcut (the hull of the set A must cover, the lcm, plain
set algebra) which the fast solver uses, and a brute-force sweep over candidate
values of A which the naive solver uses — and which also proves the extremum is
attained just once.
"""

from __future__ import annotations

from math import gcd
from typing import Any

from egegen.core.errors import GenerationFailedError
from egegen.core.generator import Generator
from egegen.core.registry import register
from egegen.core.rng import Rng
from egegen.core.templates import render
from egegen.core.types import Instance, Uniqueness

GRID_MAX = 24
BIT_LIMIT = 256


class Task15(Generator):
    task_no = 15
    answer_kind = "int"
    checker = "exact"
    uniqueness = Uniqueness.ENUMERATED
    generation_budget_ms = 300

    def build(self, rng: Rng, difficulty: int, subtype: str) -> Instance:
        for _ in range(60):
            candidate = self._attempt(rng, difficulty, subtype)
            if candidate is not None:
                return candidate
            rng = rng.fork("retry")
        raise GenerationFailedError(f"t15/{subtype}: no instance with a unique extremum")

    def _attempt(self, rng: Rng, difficulty: int, subtype: str) -> Instance | None:
        builder = {
            "15.1_segments": self._segments,
            "15.2_del": self._divisibility,
            "15.3_sets": self._sets,
            "15.4_bitwise": self._bitwise,
        }.get(subtype)
        if builder is None:
            return None
        built = builder(rng, difficulty)
        if built is None:
            return None
        meta, fields = built
        meta["subtype"] = subtype

        answer = self.solve_fast(meta)
        if not answer:
            return None
        valid = self.enumerate_answers(meta)
        if valid != [answer]:
            return None

        template = self.templates.pick(rng, subtype)
        return Instance(
            task_no=self.task_no,
            subtype=subtype,
            difficulty=difficulty,
            seed=0,
            statement_md=render(template, **fields),
            answer=answer,
            solution_steps=self._solution(meta, answer),
            reference_code=self._reference_code(meta),
            template_id=template.id,
            meta=meta,
        )

    # -- subtype builders ---------------------------------------------------
    def _segments(self, rng: Rng, difficulty: int) -> tuple[dict[str, Any], dict[str, Any]] | None:
        p1 = rng.randint(2, 14)
        p2 = p1 + rng.randint(4, 12)
        q1 = rng.randint(2, 16)
        q2 = q1 + rng.randint(3, 10)
        if q2 > GRID_MAX or p2 > GRID_MAX:
            return None
        meta = {
            "question": "segment_min_length",
            "p": [p1, p2],
            "q": [q1, q2],
            "shape": "cover" if difficulty <= 3 else "cover_both",
        }
        fields = {"p1": p1, "p2": p2, "q1": q1, "q2": q2}
        return meta, fields

    def _divisibility(
        self, rng: Rng, difficulty: int
    ) -> tuple[dict[str, Any], dict[str, Any]] | None:
        a = rng.choice([6, 10, 12, 14, 15, 18, 20, 21, 22, 24, 26, 28, 33, 35])
        b = rng.choice([9, 12, 14, 15, 16, 20, 21, 25, 27, 30, 34, 39])
        if a == b:
            return None
        lcm = a * b // gcd(a, b)
        # The brute-force check sweeps A up to the lcm and x to a few multiples of
        # it; keeping the lcm small keeps that sweep inside a fraction of a second.
        if not 24 <= lcm <= 210:
            return None
        meta = {"question": "del_max", "a": a, "b": b, "lcm": lcm}
        return meta, {"a": a, "b": b}

    def _sets(self, rng: Rng, difficulty: int) -> tuple[dict[str, Any], dict[str, Any]] | None:
        universe = sorted(rng.sample(range(1, 40), 10 + difficulty))
        p = sorted(rng.sample(universe, rng.randint(4, 6)))
        q = sorted(rng.sample(universe, rng.randint(4, 7)))
        r = sorted(set(p) | set(rng.sample(universe, rng.randint(3, 6))))
        meta = {"question": "set_min_sum", "universe": universe, "p": p, "q": q, "r": r}
        return meta, {
            "universe": ", ".join(str(x) for x in universe),
            "p": ", ".join(str(x) for x in p),
            "q": ", ".join(str(x) for x in q),
            "r": ", ".join(str(x) for x in r),
        }

    def _bitwise(self, rng: Rng, difficulty: int) -> tuple[dict[str, Any], dict[str, Any]] | None:
        a = rng.randint(3, 60)
        b = rng.randint(3, 60)
        if a == b:
            return None
        meta = {"question": "bitwise_min", "a": a, "b": b}
        return meta, {"a": a, "b": b}

    # -- solving ------------------------------------------------------------
    def _grid(self) -> list[float]:
        """Half-integer grid: segment endpoints are integers, so this catches every
        boundary the formula can turn on."""
        return [i / 2 for i in range(0, GRID_MAX * 2 + 1)]

    def _must_cover(self, meta: dict[str, Any]) -> list[float]:
        """Points x that force ``x`` to lie in A, for the segment subtypes."""
        p1, p2 = meta["p"]
        q1, q2 = meta["q"]
        out: list[float] = []
        for x in self._grid():
            in_p = p1 <= x <= p2
            in_q = q1 <= x <= q2
            need = (in_p and not in_q) if meta["shape"] == "cover" else (in_p != in_q)
            if need:
                out.append(x)
        return out

    def solve_fast(self, meta: dict[str, Any]) -> str:
        """Structural shortcut: the hull, the lcm, or plain set algebra."""
        match meta["question"]:
            case "segment_min_length":
                needed = self._must_cover(meta)
                if not needed:
                    return ""
                length = max(needed) - min(needed)
                return "" if length <= 0 or length != int(length) else str(int(length))
            case "del_max":
                a, b = meta["a"], meta["b"]
                return str(a * b // gcd(a, b))
            case "set_min_sum":
                required = set(meta["p"]) & set(meta["q"])
                if not required or not required <= set(meta["r"]):
                    return ""
                return str(sum(required))
            case "bitwise_min":
                blocked = [
                    x for x in range(BIT_LIMIT) if (x & meta["a"]) != 0 and (x & meta["b"]) != 0
                ]
                for candidate in range(1, BIT_LIMIT):
                    if all(x & candidate for x in blocked):
                        return str(candidate)
                return ""
        raise ValueError(meta["question"])

    def solve_naive(self, meta: dict[str, Any]) -> str | None:
        """Sweep every candidate A and test the formula at every point of the domain."""
        valid = self._valid_parameters(meta)
        if not valid:
            return None
        match meta["question"]:
            case "segment_min_length" | "bitwise_min" | "set_min_sum":
                return str(min(valid))
            case "del_max":
                return str(max(valid))
        return None

    def _valid_parameters(self, meta: dict[str, Any]) -> list[int]:
        """Every A that makes the formula identically true, as a plain search."""
        match meta["question"]:
            case "segment_min_length":
                p1, p2 = meta["p"]
                q1, q2 = meta["q"]
                grid = self._grid()
                lengths: set[int] = set()
                for i, a in enumerate(grid):
                    for b in grid[i:]:
                        ok = True
                        for x in grid:
                            in_p = p1 <= x <= p2
                            in_q = q1 <= x <= q2
                            in_a = a <= x <= b
                            premise = (
                                (in_p and not in_q) if meta["shape"] == "cover" else (in_p != in_q)
                            )
                            if premise and not in_a:
                                ok = False
                                break
                        if ok and (b - a) == int(b - a):
                            lengths.add(int(b - a))
                return sorted(lengths)[:1] if lengths else []
            case "del_max":
                a, b, lcm = meta["a"], meta["b"], meta["lcm"]
                domain = range(1, lcm * 4)
                return [
                    A
                    for A in range(1, lcm + 1)
                    if all((x % a != 0) or (x % b != 0) or (x % A == 0) for x in domain)
                ]
            case "set_min_sum":
                from itertools import combinations

                universe = meta["universe"]
                best: list[int] = []
                for size in range(0, len(universe) + 1):
                    hits = [
                        sum(combo)
                        for combo in combinations(universe, size)
                        if self._set_formula_holds(set(combo), meta)
                    ]
                    if hits:
                        best = [min(hits)]
                        break
                return best
            case "bitwise_min":
                return [
                    A
                    for A in range(1, BIT_LIMIT)
                    if all(
                        (x & meta["a"]) == 0 or (x & meta["b"]) == 0 or (x & A) != 0
                        for x in range(BIT_LIMIT)
                    )
                ]
        return []

    def _set_formula_holds(self, candidate: set[int], meta: dict[str, Any]) -> bool:
        p, q, r = set(meta["p"]), set(meta["q"]), set(meta["r"])
        for x in meta["universe"]:
            premise = x in p and x in q
            if premise and x not in candidate:
                return False
            if x in candidate and x not in r:
                return False
        return True

    def enumerate_answers(self, meta: dict[str, Any]) -> list[str] | None:
        values = self._valid_parameters(meta)
        if not values:
            return []
        if meta["question"] == "del_max":
            return [str(max(values))]
        return [str(min(values))]

    def validate_answer(self, answer: str, meta: dict[str, Any]) -> None:
        if not answer:
            raise ValueError("t15: no parameter satisfies the formula")
        if meta["question"] == "del_max" and int(answer) <= 1:
            raise ValueError("t15: DEL(x, 1) is always true — a trivial answer")

    # -- explanation --------------------------------------------------------
    def _reference_code(self, meta: dict[str, Any]) -> str:
        match meta["question"]:
            case "segment_min_length":
                p1, p2 = meta["p"]
                q1, q2 = meta["q"]
                premise = (
                    f"seg(x, {p1}, {p2}) and not seg(x, {q1}, {q2})"
                    if meta["shape"] == "cover"
                    else f"seg(x, {p1}, {p2}) != seg(x, {q1}, {q2})"
                )
                return (
                    "def seg(x, a, b): return a <= x <= b\n"
                    "best = None\n"
                    "xs = [i / 2 for i in range(0, 61)]     # шаг 0.5 — чтобы не "
                    "пропустить границы\n"
                    "for i, a in enumerate(xs):\n"
                    "    for b in xs[i:]:\n"
                    f"        if all((not ({premise})) or seg(x, a, b) for x in xs):\n"
                    "            if best is None or b - a < best: best = b - a\n"
                    "print(best)\n"
                )
            case "del_max":
                a, b, lcm = meta["a"], meta["b"], meta["lcm"]
                return (
                    "def DEL(x, a): return x % a == 0\n"
                    f"print(max(A for A in range(1, {lcm + 1})\n"
                    f"          if all((not DEL(x, {a})) or (not DEL(x, {b})) "
                    "or DEL(x, A)\n"
                    f"                 for x in range(1, {lcm * 4}))))\n"
                )
            case "set_min_sum":
                return (
                    "from itertools import combinations\n"
                    f"P = {sorted(meta['p'])}\nQ = {sorted(meta['q'])}\n"
                    f"R = {sorted(meta['r'])}\nU = {sorted(meta['universe'])}\n"
                    "def ok(A):\n"
                    "    return all(not (x in P and x in Q) or x in A for x in U) and \\\n"
                    "           all(x in R for x in A)\n"
                    "best = None\n"
                    "for k in range(len(U) + 1):\n"
                    "    for c in combinations(U, k):\n"
                    "        if ok(set(c)) and (best is None or sum(c) < best):\n"
                    "            best = sum(c)\n"
                    "    if best is not None: break\n"
                    "print(best)\n"
                )
            case "bitwise_min":
                a, b = meta["a"], meta["b"]
                return (
                    "def bit(x, m): return (x & m) != 0\n"
                    f"print(min(A for A in range(1, 256)\n"
                    f"          if all((not bit(x, {a})) or (not bit(x, {b})) "
                    "or bit(x, A)\n"
                    "                 for x in range(0, 256))))\n"
                )
        raise ValueError(meta["question"])

    def _solution(self, meta: dict[str, Any], answer: str) -> list[str]:
        head = (
            "**Шаг 1.** «Тождественно истинна» значит «нет ни одного "
            "контрпримера». Импликация `P → Q` записывается как `(not P) or Q`, "
            "и формула проверяется **для всех** x, а не для одного."
        )
        match meta["question"]:
            case "segment_min_length":
                needed = self._must_cover(meta)
                return [
                    head,
                    "**Шаг 2.** Разберёмся, что формула требует от A. Она нарушается "
                    "только там, где посылка истинна, а x не попал в A. Значит, "
                    "A обязан накрыть все такие x. Здесь это отрезок от "
                    f"{min(needed):g} до {max(needed):g}.",
                    "**Шаг 3.** Наименьший отрезок, накрывающий их, — именно этот, "
                    f"его длина **{answer}**. Перебор с шагом 0,5 даёт тот же "
                    "результат:\n\n```python\n" + self._reference_code(meta) + "```",
                ]
            case "del_max":
                a, b = meta["a"], meta["b"]
                lcm = a * b // gcd(a, b)
                return [
                    head,
                    f"**Шаг 2.** Посылка истинна ровно тогда, когда x делится и на "
                    f"{a}, и на {b}, то есть на НОК({a}, {b}) = {lcm}. Для всех таких "
                    "x требуется, чтобы x делился на A.",
                    f"**Шаг 3.** Значит, A должен быть делителем {lcm}, и наибольшее "
                    f"такое A — само **{answer}**. A = 1 подходит всегда, поэтому "
                    "спрашивают именно наибольшее значение.",
                    "```python\n" + self._reference_code(meta) + "```",
                ]
            case "set_min_sum":
                required = sorted(set(meta["p"]) & set(meta["q"]))
                return [
                    head,
                    "**Шаг 2.** Первая часть формулы требует, чтобы A содержало все "
                    f"элементы пересечения P и Q: {required}. Вторая часть требует, "
                    "чтобы A целиком лежало внутри R.",
                    f"**Шаг 3.** Наименьшее подходящее A — это само пересечение, "
                    f"а сумма его элементов равна **{answer}**.",
                    "```python\n" + self._reference_code(meta) + "```",
                ]
            case "bitwise_min":
                return [
                    head,
                    "**Шаг 2.** Формула нарушается на тех x, у которых есть общие "
                    f"биты и с {meta['a']}, и с {meta['b']}. Для каждого такого x "
                    "нужно, чтобы A имел с ним хотя бы один общий бит.",
                    "**Шаг 3.** Перебираем A по возрастанию и берём первое "
                    f"подходящее: **{answer}**. В побитовых условиях обязательно "
                    "ставьте скобки: `(x & A) == 0`.",
                    "```python\n" + self._reference_code(meta) + "```",
                ]
        return [head]


register(Task15())
