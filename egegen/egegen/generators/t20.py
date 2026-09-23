"""Task 20 — Petya wins with his second move, but not his first (predicate W2).

The exam asks for **two** values here, so the generator only releases a game whose
W2 set has exactly two members.
"""

from __future__ import annotations

from typing import Any

from egegen.core.registry import register
from egegen.core.types import AnswerKind
from egegen.generators.t19 import Task19


class Task20(Task19):
    task_no = 20
    answer_kind: AnswerKind = "two_ints"
    checker = "int_pair_ordered"
    predicate = "W2"

    def _accepts(self, values: list[int]) -> bool:
        return len(values) >= 2

    def _format(self, values: list[int]) -> str:
        # Some games (one pile, +k and xk) never have exactly two W2 positions; the
        # statement then asks for the two smallest, which is still unambiguous.
        return " ".join(str(v) for v in sorted(values)[:2])

    def count_hint(self, values: list[int]) -> str:
        return "два" if len(values) == 2 else "два наименьших"

    def _solution(self, meta: dict[str, Any], values: list[int], answer: str) -> list[str]:
        return [
            "**Шаг 1.** Тот же шаблон W1 / L1 / W2 / L2, что и в 19-м задании: "
            "меняется только печатаемый предикат.",
            "**Шаг 2.** Здесь нужен **W2**: Петя не может выиграть первым ходом, "
            "но у него есть ход в позицию L1 — тогда при любом ответе Вани Петя "
            "выигрывает своим вторым ходом. Обратите внимание: `W2` требует "
            "`not W1` — иначе в ответ попадут позиции, где Петя выигрывает сразу.\n\n"
            "```python\n" + self._reference_code(meta) + "```",
            (
                f"**Шаг 3.** Программа печатает {values}. "
                + (
                    "Подходящих значений ровно два"
                    if len(values) == 2
                    else "По условию берём два наименьших из них"
                )
                + f": **{answer}**. Записываем их в порядке возрастания "
                "через пробел, в одной строке."
            ),
        ]


register(Task20())
