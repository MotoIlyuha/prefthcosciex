"""Task 21 — Vanya wins with his first or second move, but cannot guarantee the first.

That is the predicate L2, and the exam asks for the smallest such S.
"""

from __future__ import annotations

from typing import Any

from egegen.core.registry import register
from egegen.core.types import AnswerKind
from egegen.generators.t19 import Task19


class Task21(Task19):
    task_no = 21
    answer_kind: AnswerKind = "int"
    checker = "exact"
    predicate = "L2"

    def _accepts(self, values: list[int]) -> bool:
        return len(values) >= 1

    def _solution(self, meta: dict[str, Any], values: list[int], answer: str) -> list[str]:
        return [
            "**Шаг 1.** Шаблон тот же, что в 19-м и 20-м заданиях — меняется печатаемый предикат.",
            "**Шаг 2.** Здесь нужен **L2**: у Пети нет выигрыша первым ходом "
            "(`not W1`) и нет позиции L1 (`not L1`), а после любого его хода Ваня "
            "выигрывает первым или вторым ходом (`W1(m) or W2(m)`). Именно это "
            "означает «Ваня выигрывает первым или вторым ходом, но не может "
            "гарантированно выиграть первым».\n\n"
            "```python\n" + self._reference_code(meta) + "```",
            f"**Шаг 3.** Программа печатает {values}; по условию берём наименьшее "
            f"значение — **{answer}**.",
        ]


register(Task21())
