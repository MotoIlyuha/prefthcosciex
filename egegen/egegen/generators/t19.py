"""Task 19 — the base game question: Vanya wins with his very first move."""

from __future__ import annotations

from typing import Any

from egegen.core.errors import GenerationFailedError
from egegen.core.generator import Generator
from egegen.core.registry import register
from egegen.core.rng import Rng
from egegen.core.templates import render
from egegen.core.types import AnswerKind, Instance, Uniqueness
from egegen.generators._games import (
    describe_end,
    describe_moves,
    describe_start,
    scan,
    scan_naive,
    spec_candidates,
)


class Task19(Generator):
    task_no = 19
    answer_kind: AnswerKind = "int"
    checker: str = "exact"
    uniqueness = Uniqueness.ENUMERATED
    generation_budget_ms = 400

    predicate = "L1"

    def count_hint(self, values: list[int]) -> str:
        """Filled into the question when the number of answers needs spelling out."""
        return ""

    def build(self, rng: Rng, difficulty: int, subtype: str) -> Instance:
        for spec in spec_candidates(rng.fork("specs"), subtype, difficulty):
            candidate = self._attempt(rng, difficulty, subtype, spec)
            if candidate is not None:
                return candidate
        raise GenerationFailedError(f"t{self.task_no}/{subtype}: no game with the required shape")

    def _attempt(
        self, rng: Rng, difficulty: int, subtype: str, spec: dict[str, Any]
    ) -> Instance | None:
        values = scan(spec, self.predicate)
        if not self._accepts(values):
            return None
        meta: dict[str, Any] = {
            "subtype": subtype,
            "spec": spec,
            "predicate": self.predicate,
        }
        answer = self._format(values)
        template = self.templates.pick(rng, subtype)
        statement = render(
            template,
            moves=describe_moves(spec),
            ending=describe_end(spec),
            start=describe_start(spec),
            target=spec["target"],
            count_hint=self.count_hint(values),
        )
        return Instance(
            task_no=self.task_no,
            subtype=subtype,
            difficulty=difficulty,
            seed=0,
            statement_md=statement,
            answer=answer,
            solution_steps=self._solution(meta, values, answer),
            reference_code=self._reference_code(meta),
            template_id=template.id,
            meta=meta,
        )

    def _accepts(self, values: list[int]) -> bool:
        return len(values) >= 1

    def _format(self, values: list[int]) -> str:
        return str(min(values))

    # -- solving ------------------------------------------------------------
    def solve_fast(self, meta: dict[str, Any]) -> str:
        return self._format(scan(meta["spec"], meta["predicate"]))

    def solve_naive(self, meta: dict[str, Any]) -> str | None:
        values = scan_naive(meta["spec"], meta["predicate"])
        return self._format(values) if self._accepts(values) else None

    def enumerate_answers(self, meta: dict[str, Any]) -> list[str] | None:
        values = scan(meta["spec"], meta["predicate"])
        return [self._format(values)] if self._accepts(values) else []

    def validate_answer(self, answer: str, meta: dict[str, Any]) -> None:
        if not answer:
            raise ValueError(f"t{self.task_no}: empty answer")

    # -- explanation --------------------------------------------------------
    def _reference_code(self, meta: dict[str, Any]) -> str:
        spec = meta["spec"]
        target = spec["target"]
        if spec["kind"] == "two_piles":
            moves = (
                "def moves(s):\n"
                "    a, b = s\n"
                "    return ["
                + ", ".join(
                    [f"(a + {k}, b), (a, b + {k})" for k in spec["adds"]]
                    + [f"(a * {k}, b), (a, b * {k})" for k in spec["muls"]]
                )
                + "]\n"
                f"def over(s): return s[0] + s[1] >= {target}\n"
                f"states = [({spec['fixed']}, k) for k in range(1, {target})]\n"
                "value = lambda s: s[1]\n"
            )
        elif spec["kind"] == "decreasing":
            moves = (
                "def moves(s):\n"
                f"    return [s - k for k in {spec['subs']} if s - k >= 0]\n"
                "def over(s): return s == 0\n"
                f"states = list(range(1, {target} + 1))\n"
                "value = lambda s: s\n"
            )
        else:
            moves = (
                "def moves(s):\n"
                "    return ["
                + ", ".join([f"s + {k}" for k in spec["adds"]] + [f"s * {k}" for k in spec["muls"]])
                + "]\n"
                f"def over(s): return s >= {target}\n"
                f"states = list(range(1, {target}))\n"
                "value = lambda s: s\n"
            )
        return (
            "from functools import lru_cache\n\n"
            + moves
            + "\n@lru_cache(None)\ndef W1(s): return any(over(m) for m in moves(s))\n"
            "@lru_cache(None)\ndef L1(s):\n"
            "    ms = moves(s)\n"
            "    return bool(ms) and not W1(s) and all(W1(m) for m in ms)\n"
            "@lru_cache(None)\ndef W2(s): return not W1(s) and any(L1(m) for m in moves(s))\n"
            "@lru_cache(None)\ndef L2(s):\n"
            "    ms = moves(s)\n"
            "    return (bool(ms) and not W1(s) and not L1(s)\n"
            "            and all(W1(m) or W2(m) for m in ms))\n\n"
            f"print(sorted(value(s) for s in states if {meta['predicate']}(s)))\n"
        )

    def _solution(self, meta: dict[str, Any], values: list[int], answer: str) -> list[str]:
        return [
            "**Шаг 1.** Все три игровых задания решаются одним шаблоном W1 / L1 / W2 / L2. "
            "Меняются только функция ходов `moves`, условие окончания `over` и то, "
            "какой предикат печатаем.",
            "**Шаг 2.** Здесь спрашивают про **L1**: Петя не может выиграть первым "
            "ходом, а после любого его хода Ваня выигрывает своим первым ходом.\n\n"
            "```python\n" + self._reference_code(meta) + "```",
            f"**Шаг 3.** Программа печатает {values}. "
            f"По условию берём наименьшее значение: **{answer}**.",
        ]


register(Task19())
