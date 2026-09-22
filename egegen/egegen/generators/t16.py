"""Task 16 — recurrence relations.

The recurrence is data, not code: a family plus a few numbers. The fast solver
evaluates it bottom-up in an array, the naive one recurses with ``lru_cache`` after
raising the recursion limit — the two ways the exam's own template suggests.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from egegen.core.deeprec import run_deep
from egegen.core.errors import GenerationFailed
from egegen.core.generator import Generator
from egegen.core.registry import register
from egegen.core.rng import Rng
from egegen.core.templates import render
from egegen.core.types import Instance, Uniqueness

MAX_DIGITS = 40


class Task16(Generator):
    task_no = 16
    answer_kind = "int"
    checker = "exact"
    requires_code = True
    uniqueness = Uniqueness.FUNCTIONAL

    def build(self, rng: Rng, difficulty: int, subtype: str) -> Instance:
        for _ in range(60):
            candidate = self._attempt(rng, difficulty, subtype)
            if candidate is not None:
                return candidate
            rng = rng.fork("retry")
        raise GenerationFailed(f"t16/{subtype}: no valid instance")

    def _attempt(self, rng: Rng, difficulty: int, subtype: str) -> Instance | None:
        spec = self._random_spec(rng, difficulty, subtype)
        if spec is None:
            return None
        meta: dict[str, Any] = {"subtype": subtype, "spec": spec}

        match subtype:
            case "16.1_value":
                meta["question"] = "value"
                meta["n"] = self._pick_n(rng, spec, difficulty)
            case "16.2_difference":
                meta["question"] = "difference"
                hi = self._pick_n(rng, spec, difficulty)
                meta["n"], meta["n2"] = hi, hi - rng.choice([1, 2, 3])
            case "16.3_parity_branch":
                meta["question"] = "value"
                meta["n"] = self._pick_n(rng, spec, difficulty)
            case "16.4_call_count":
                meta["question"] = "calls"
                meta["n"] = rng.randint(12, 26)
            case "16.5_two_args":
                meta["question"] = "two_args"
                meta["n"] = rng.randint(5, 9 + difficulty)
                meta["n2"] = rng.randint(4, 8 + difficulty)
            case _:
                return None

        answer = self.solve_fast(meta)
        if not answer or len(answer.lstrip("-")) > MAX_DIGITS:
            return None
        if abs(int(answer)) < 2:
            return None

        template = self.templates.pick(rng, subtype)
        fields = {
            "definition": self._describe(spec),
            "code": self._pseudo_code(spec),
            "n": meta["n"],
            "n2": meta.get("n2", 0),
        }
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

    def _random_spec(
        self, rng: Rng, difficulty: int, subtype: str
    ) -> dict[str, Any] | None:
        match subtype:
            case "16.3_parity_branch":
                family = "parity"
            case "16.4_call_count":
                family = "two_branch"
            case "16.5_two_args":
                family = "two_args"
            case _:
                family = rng.choice(["shift_add", "shift_mul", "halving"])
        spec: dict[str, Any] = {
            "family": family,
            "base_n": rng.randint(1, 2),
            "base_value": rng.randint(1, 5),
            "a": rng.randint(2, 5),
            "b": rng.randint(1, 9),
        }
        if family == "shift_mul":
            spec["a"] = 2
        return spec

    def _pick_n(self, rng: Rng, spec: dict[str, Any], difficulty: int) -> int:
        if spec["family"] == "shift_mul":
            # Doubling every step: beyond ~120 the value passes 40 digits.
            return rng.randint(30, 110)
        if spec["family"] == "halving":
            return rng.choice([2027, 4096, 10_000, 65_536, 100_000])
        return rng.choice([500, 1000, 1500, 2025, 2026, 2027, 2500, 3000])

    # -- recurrence semantics ----------------------------------------------
    def _step(self, spec: dict[str, Any], n: int, previous: int) -> int:
        a, b = spec["a"], spec["b"]
        match spec["family"]:
            case "shift_add":
                return previous + a * n + b
            case "shift_mul":
                return previous * a + b
            case "parity":
                return previous + a * n if n % 2 == 0 else previous + b
            case "halving":
                return previous + a * n + b
        raise ValueError(spec["family"])

    def _evaluate_bottom_up(self, spec: dict[str, Any], n: int) -> int:
        """Iterative evaluation from the base case upward — no recursion at all."""
        base_n, base_value = spec["base_n"], spec["base_value"]
        if n <= base_n:
            return base_value
        if spec["family"] == "halving":
            chain: list[int] = []
            current = n
            while current > base_n:
                chain.append(current)
                current //= 2
            value = base_value
            for step_n in reversed(chain):
                value = self._step(spec, step_n, value)
            return value
        value = base_value
        for step_n in range(base_n + 1, n + 1):
            value = self._step(spec, step_n, value)
        return value

    def _evaluate_recursive(self, spec: dict[str, Any], n: int) -> int:
        """Memoised recursion, as the method card teaches.

        Run on a big-stack thread: raising ``sys.setrecursionlimit`` alone is not
        enough once the chain is a few thousand frames deep.
        """
        base_n, base_value = spec["base_n"], spec["base_value"]
        halving = spec["family"] == "halving"
        memo: dict[int, int] = {}

        def f(k: int) -> int:
            if k <= base_n:
                return base_value
            if k not in memo:
                memo[k] = self._step(spec, k, f(k // 2 if halving else k - 1))
            return memo[k]

        # A plain dict memo rather than lru_cache on purpose: every lru_cache call
        # consumes CPython's C-recursion budget, which setrecursionlimit does not
        # raise, so a cached chain recursion dies around depth 3300 (measured on
        # 3.12) while this one follows the ordinary recursion limit.
        return run_deep(lambda: f(n))

    def _count_calls_dp(self, spec: dict[str, Any], n: int) -> int:
        """Number of F(...) invocations, counted bottom-up.

        The values are not cached on purpose: caching would make the recursion visit
        each argument once and hide exactly what the question asks about.
        """
        base_n = spec["base_n"]
        counts: dict[int, int] = {}
        for k in range(0, n + 1):
            if k <= base_n:
                counts[k] = 1
            else:
                counts[k] = 1 + counts[k - 1] + counts.get(k - 2, 1)
        return counts[n]

    def _count_calls_recursive(self, spec: dict[str, Any], n: int) -> int:
        base_n = spec["base_n"]

        @lru_cache(maxsize=None)
        def calls(k: int) -> int:
            if k <= base_n:
                return 1
            return 1 + calls(k - 1) + calls(max(k - 2, 0))

        return run_deep(lambda: calls(n))

    def _two_args_dp(self, a: int, b: int) -> int:
        grid = [[1] * (b + 1) for _ in range(a + 1)]
        for i in range(1, a + 1):
            for j in range(1, b + 1):
                grid[i][j] = grid[i - 1][j] + grid[i][j - 1]
        return grid[a][b]

    def _two_args_recursive(self, a: int, b: int) -> int:
        @lru_cache(maxsize=None)
        def f(i: int, j: int) -> int:
            if i == 0 or j == 0:
                return 1
            return f(i - 1, j) + f(i, j - 1)

        return run_deep(lambda: f(a, b))

    # -- solving ------------------------------------------------------------
    def solve_fast(self, meta: dict[str, Any]) -> str:
        spec = meta["spec"]
        match meta["question"]:
            case "value":
                return str(self._evaluate_bottom_up(spec, meta["n"]))
            case "difference":
                return str(
                    self._evaluate_bottom_up(spec, meta["n"])
                    - self._evaluate_bottom_up(spec, meta["n2"])
                )
            case "calls":
                return str(self._count_calls_dp(spec, meta["n"]))
            case "two_args":
                return str(self._two_args_dp(meta["n"], meta["n2"]))
        raise ValueError(meta["question"])

    def solve_naive(self, meta: dict[str, Any]) -> str | None:
        spec = meta["spec"]
        match meta["question"]:
            case "value":
                return str(self._evaluate_recursive(spec, meta["n"]))
            case "difference":
                return str(
                    self._evaluate_recursive(spec, meta["n"])
                    - self._evaluate_recursive(spec, meta["n2"])
                )
            case "calls":
                return str(self._count_calls_recursive(spec, meta["n"]))
            case "two_args":
                return str(self._two_args_recursive(meta["n"], meta["n2"]))
        return None

    def validate_answer(self, answer: str, meta: dict[str, Any]) -> None:
        if len(answer.lstrip("-")) > MAX_DIGITS:
            raise ValueError("t16: answer exceeds 40 digits")

    # -- statement helpers --------------------------------------------------
    def _describe(self, spec: dict[str, Any]) -> str:
        a, b, base_n, base_value = spec["a"], spec["b"], spec["base_n"], spec["base_value"]
        match spec["family"]:
            case "shift_add":
                return (
                    f"F(n) = {base_value}, если n ≤ {base_n};\n\n"
                    f"F(n) = F(n − 1) + {a}·n + {b}, если n > {base_n}."
                )
            case "shift_mul":
                return (
                    f"F(n) = {base_value}, если n ≤ {base_n};\n\n"
                    f"F(n) = {a}·F(n − 1) + {b}, если n > {base_n}."
                )
            case "parity":
                return (
                    f"F(n) = {base_value}, если n ≤ {base_n};\n\n"
                    f"F(n) = F(n − 1) + {a}·n, если n > {base_n} и n чётно;\n\n"
                    f"F(n) = F(n − 1) + {b}, если n > {base_n} и n нечётно."
                )
            case "halving":
                return (
                    f"F(n) = {base_value}, если n ≤ {base_n};\n\n"
                    f"F(n) = F(n // 2) + {a}·n + {b}, если n > {base_n} "
                    "(здесь // — целочисленное деление)."
                )
            case "two_branch":
                return (
                    f"F(n) = {base_value}, если n ≤ {base_n};\n\n"
                    f"F(n) = F(n − 1) + F(n − 2) + {b}, если n > {base_n}."
                )
            case "two_args":
                return (
                    "F(a, b) = 1, если a = 0 или b = 0;\n\n"
                    "F(a, b) = F(a − 1, b) + F(a, b − 1) в остальных случаях."
                )
        return ""

    def _pseudo_code(self, spec: dict[str, Any]) -> str:
        return self._describe(spec)

    def _reference_code(self, meta: dict[str, Any]) -> str:
        spec = meta["spec"]
        base_n, base_value = spec["base_n"], spec["base_value"]
        a, b = spec["a"], spec["b"]
        chain_step = {
            "shift_add": f"        value = value + {a} * k + {b}",
            "shift_mul": f"        value = {a} * value + {b}",
            "parity": (
                f"        value = value + {a} * k if k % 2 == 0 "
                f"else value + {b}"
            ),
        }
        if spec["family"] in chain_step:
            # Bottom-up, not recursion: the chain is a few thousand deep and a
            # memoised recursion of that depth raises RecursionError in CPython 3.12
            # (and therefore in Pyodide) no matter what the recursion limit is.
            head = (
                "def F(n):\n"
                f"    value = {base_value}\n"
                f"    for k in range({base_n} + 1, n + 1):\n"
                f"{chain_step[spec['family']]}\n"
                "    return value\n"
            )
        else:
            head = (
                "import sys\nsys.setrecursionlimit(100_000)\n"
                "from functools import lru_cache\n\n@lru_cache(None)\ndef F(n):\n"
                f"    if n <= {base_n}: return {base_value}\n"
                f"    return F(n // 2) + {a} * n + {b}\n"
            )
        match spec["family"]:
            case "two_branch":
                head = (
                    "from functools import lru_cache\n\n@lru_cache(None)\n"
                    "def calls(n):\n"
                    f"    if n <= {base_n}: return 1\n"
                    "    return 1 + calls(n - 1) + calls(max(n - 2, 0))\n"
                )
                return head + f"print(calls({meta['n']}))\n"
            case "two_args":
                head = (
                    "from functools import lru_cache\n\n@lru_cache(None)\n"
                    "def F(a, b):\n"
                    "    if a == 0 or b == 0: return 1\n"
                    "    return F(a - 1, b) + F(a, b - 1)\n"
                )
                return head + f"print(F({meta['n']}, {meta['n2']}))\n"
        if meta["question"] == "difference":
            return head + f"print(F({meta['n']}) - F({meta['n2']}))\n"
        return head + f"print(F({meta['n']}))\n"

    def _step_two_text(self, meta: dict[str, Any]) -> str:
        chain = meta["spec"]["family"] in ("shift_add", "shift_mul", "parity")
        if chain:
            lead = (
                "**Шаг 2.** Зависимость идёт от n − 1, а n здесь — несколько тысяч. "
                "Рекурсия такой глубины падает с `RecursionError` даже после "
                "`sys.setrecursionlimit`, поэтому считаем **снизу вверх** обычным "
                "циклом — это и быстрее, и надёжнее."
            )
        else:
            lead = (
                "**Шаг 2.** Обязательно `@lru_cache(None)` — без него ветвящаяся "
                "рекурсия зависнет, — и `sys.setrecursionlimit(100_000)`. Глубина "
                "здесь небольшая, поэтому рекурсия подходит."
            )
        return lead + "\n\n```python\n" + self._reference_code(meta) + "```"

    def _solution(self, meta: dict[str, Any], answer: str) -> list[str]:
        spec = meta["spec"]
        notes = [
            "**Шаг 1.** Перепишите определение как функцию Python — один в один, "
            "не упрощая его алгебраически.",
            self._step_two_text(meta),
        ]
        if meta["question"] == "calls":
            notes[1] = (
                "**Шаг 2.** Здесь считают **вызовы**, а не значения. Кэшировать "
                "значения нельзя — часть вызовов «исчезнет». Кэшируйте само "
                "количество вызовов:\n\n```python\n"
                + self._reference_code(meta)
                + "```"
            )
        if spec["family"] == "halving":
            notes.append(
                "**Шаг 3.** Зависимость идёт от n // 2, поэтому цепочка коротка "
                "(около log₂ n шагов) — можно посчитать и в столбик, но кодом "
                "надёжнее."
            )
        notes.append(f"**Ответ:** **{answer}**.")
        return notes


register(Task16())
