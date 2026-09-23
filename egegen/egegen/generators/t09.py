"""Task 9 — counting rows of a spreadsheet that satisfy a numeric condition.

Sorting each row first turns almost every condition the exam uses into a one-liner:
``a[0] + a[1]`` are the two smallest, ``a[-1]`` the largest, ``len(set(a))`` says how
many repeats there are. The naive solver expresses the same conditions through
``Counter`` and explicit min/max instead, so a mis-stated "exactly one pair" cannot
pass both.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from egegen.core.errors import GenerationFailedError
from egegen.core.generator import Generator
from egegen.core.registry import register
from egegen.core.rng import Rng
from egegen.core.tables import Cell, preview, to_csv, to_ods
from egegen.core.templates import render
from egegen.core.types import Attachment, Instance, Uniqueness


class Task09(Generator):
    task_no = 9
    answer_kind = "int"
    checker = "exact"
    requires_code = True
    uniqueness = Uniqueness.FUNCTIONAL
    generation_budget_ms = 400

    def build(self, rng: Rng, difficulty: int, subtype: str) -> Instance:
        for _ in range(25):
            candidate = self._attempt(rng, difficulty, subtype)
            if candidate is not None:
                return candidate
            rng = rng.fork("retry")
        raise GenerationFailedError(f"t09/{subtype}: no instance with a usable row count")

    def _attempt(self, rng: Rng, difficulty: int, subtype: str) -> Instance | None:
        columns = rng.randint(4, 6)
        rows_count = rng.choice([3000, 4000, 5000])
        repeat_share = 0.12 if subtype == "9.2_one_repeat" else 0.2
        table = [self._random_row(rng, columns, repeat_share) for _ in range(rows_count)]
        # The doc wants the answer in [3, N/4]: fewer and it is luck, more and the
        # condition stops selecting. Rather than re-rolling the whole table, try the
        # candidate thresholds for this subtype and keep the first one that lands.
        meta: dict[str, Any] = {"subtype": subtype, "table": table, "columns": columns}
        chosen: dict[str, Any] | None = None
        for candidate in self._condition_candidates(rng, difficulty, subtype, columns):
            meta["condition"] = candidate
            count = int(self.solve_fast(meta))
            if 3 <= count <= rows_count // 4:
                chosen = candidate
                break
        if chosen is None:
            return None
        meta["condition"] = chosen
        answer = self.solve_fast(meta)

        header: list[Cell] = [f"Столбец {i + 1}" for i in range(columns)]
        data: list[list[Cell]] = [header]
        data.extend([int(v) for v in row] for row in table)
        template = self.templates.pick(rng, subtype)
        return Instance(
            task_no=self.task_no,
            subtype=subtype,
            difficulty=difficulty,
            seed=0,
            statement_md=render(
                template,
                rows=rows_count,
                columns=columns,
                condition=self._describe(chosen),
                preview=preview(data, limit=5),
            ),
            answer=answer,
            solution_steps=self._solution(meta, answer),
            reference_code=self._reference_code(meta),
            template_id=template.id,
            assets=[
                Attachment("9.csv", "text/csv", "csv", to_csv(data)),
                Attachment(
                    "9.ods",
                    "application/vnd.oasis.opendocument.spreadsheet",
                    "ods",
                    to_ods(data, sheet_name="Числа"),
                ),
            ],
            meta=meta,
        )

    def _random_row(self, rng: Rng, columns: int, repeat_share: float) -> list[int]:
        row = [rng.randint(1, 100) for _ in range(columns)]
        if rng.chance(repeat_share):
            i, j = rng.sample(range(columns), 2)
            row[j] = row[i]
        return row

    def _condition_candidates(
        self, rng: Rng, difficulty: int, subtype: str, columns: int
    ) -> list[dict[str, Any]]:
        """Conditions to try, ordered by how selective they are expected to be."""
        divisors = [3, 4, 5, 6, 7]
        rng.shuffle(divisors)
        match subtype:
            case "9.1_sums":
                # a[0] + a[1] > a[-1] + a[-2] can never hold in a sorted row
                # (a[0] <= a[-2] and a[1] <= a[-1]), so the comparison is against the
                # single largest element instead.
                base = [{"kind": "two_smallest_vs_largest", "extra_divisor": d} for d in divisors]
                if difficulty <= 3:
                    base.append({"kind": "two_smallest_vs_largest", "extra_divisor": 0})
                return base
            case "9.2_one_repeat":
                out = [{"kind": "one_repeat", "extra_divisor": d} for d in divisors]
                if difficulty <= 2:
                    out.insert(0, {"kind": "one_repeat", "extra_divisor": 0})
                return out
            case "9.3_all_distinct":
                return [
                    {"kind": "all_distinct", "threshold": t}
                    for t in range(60 * columns, 90 * columns, 4)
                ][::-1]
            case "9.4_divisible":
                return [
                    {"kind": "divisible_count", "divisor": d, "at_least": m}
                    for m in range(columns, 1, -1)
                    for d in divisors
                ]
            case "9.5_average":
                return [{"kind": "average_vs_max", "factor": f} for f in (3, 2, 4)]
        return []

    def _describe(self, condition: dict[str, Any]) -> str:
        match condition["kind"]:
            case "two_smallest_vs_largest":
                tail = (
                    f", а сумма всех чисел строки делится на {condition['extra_divisor']}"
                    if condition["extra_divisor"]
                    else ""
                )
                return (
                    "сумма двух наименьших чисел строки **больше** наибольшего "
                    "числа этой строки" + tail
                )
            case "one_repeat":
                tail = (
                    f", а сумма чисел строки делится на {condition['extra_divisor']}"
                    if condition["extra_divisor"]
                    else ""
                )
                return (
                    "ровно одно число встречается в строке **дважды**, а все "
                    "остальные различны" + tail
                )
            case "all_distinct":
                return f"все числа строки различны, а их сумма больше {condition['threshold']}"
            case "divisible_count":
                return (
                    f"не менее {condition['at_least']} чисел строки делятся "
                    f"на {condition['divisor']}"
                )
            case "average_vs_max":
                return (
                    "наибольшее число строки **больше** среднего арифметического "
                    f"всех чисел строки, умноженного на {condition['factor']}"
                )
        raise ValueError(condition["kind"])

    # -- solving ------------------------------------------------------------
    def _row_ok_sorted(self, row: list[int], condition: dict[str, Any]) -> bool:
        a = sorted(row)
        match condition["kind"]:
            case "two_smallest_vs_largest":
                if not a[0] + a[1] > a[-1]:
                    return False
                divisor = int(condition["extra_divisor"])
                return not divisor or sum(a) % divisor == 0
            case "one_repeat":
                if len(set(a)) != len(a) - 1:
                    return False
                divisor = int(condition["extra_divisor"])
                return not divisor or sum(a) % divisor == 0
            case "all_distinct":
                return len(set(a)) == len(a) and sum(a) > int(condition["threshold"])
            case "divisible_count":
                divisor = int(condition["divisor"])
                hits = sum(1 for x in a if x % divisor == 0)
                return hits >= int(condition["at_least"])
            case "average_vs_max":
                # Compare by multiplication, never by float division.
                return a[-1] * len(a) > int(condition["factor"]) * sum(a)
        raise ValueError(condition["kind"])

    def _row_ok_counter(self, row: list[int], condition: dict[str, Any]) -> bool:
        counts = Counter(row)
        match condition["kind"]:
            case "two_smallest_vs_largest":
                rest = list(row)
                lo1 = min(rest)
                rest.remove(lo1)
                lo2 = min(rest)
                if not lo1 + lo2 > max(row):
                    return False
                divisor = int(condition["extra_divisor"])
                return not divisor or sum(row) % divisor == 0
            case "one_repeat":
                pairs = [v for v, n in counts.items() if n == 2]
                singles = [v for v, n in counts.items() if n == 1]
                if not (len(pairs) == 1 and len(singles) == len(row) - 2):
                    return False
                divisor = int(condition["extra_divisor"])
                return not divisor or sum(row) % divisor == 0
            case "all_distinct":
                return max(counts.values()) == 1 and sum(row) > int(condition["threshold"])
            case "divisible_count":
                divisor = int(condition["divisor"])
                return len([x for x in row if x % divisor == 0]) >= int(condition["at_least"])
            case "average_vs_max":
                return max(row) * len(row) > int(condition["factor"]) * sum(row)
        raise ValueError(condition["kind"])

    def solve_fast(self, meta: dict[str, Any]) -> str:
        return str(sum(1 for row in meta["table"] if self._row_ok_sorted(row, meta["condition"])))

    def solve_naive(self, meta: dict[str, Any]) -> str | None:
        return str(sum(1 for row in meta["table"] if self._row_ok_counter(row, meta["condition"])))

    def validate_answer(self, answer: str, meta: dict[str, Any]) -> None:
        if int(answer) < 1:
            raise ValueError("t09: no rows match")

    # -- explanation --------------------------------------------------------
    def _reference_code(self, meta: dict[str, Any]) -> str:
        condition = meta["condition"]
        test = {
            "two_smallest_vs_largest": "a[0] + a[1] > a[-1]"
            + (
                f" and sum(a) % {condition['extra_divisor']} == 0"
                if condition.get("extra_divisor")
                else ""
            ),
            "one_repeat": "len(set(a)) == len(a) - 1"
            + (
                f" and sum(a) % {condition['extra_divisor']} == 0"
                if condition.get("extra_divisor")
                else ""
            ),
            "all_distinct": f"len(set(a)) == len(a) and sum(a) > {condition.get('threshold')}",
            "divisible_count": f"sum(x % {condition.get('divisor')} == 0 for x in a) "
            f">= {condition.get('at_least')}",
            "average_vs_max": f"a[-1] * len(a) > {condition.get('factor')} * sum(a)",
        }[condition["kind"]]
        return (
            "import csv\n\ncnt = 0\n"
            "for row in list(csv.reader(open('9.csv')))[1:]:   # первая строка — заголовки\n"
            "    a = sorted(map(int, row))\n"
            f"    if {test}:\n"
            "        cnt += 1\n"
            "print(cnt)\n"
        )

    def _solution(self, meta: dict[str, Any], answer: str) -> list[str]:
        return [
            "**Шаг 1.** Отсортируйте числа строки — после этого почти любое условие "
            "записывается одной строкой: `a[0] + a[1]` — два наименьших, `a[-1]` — "
            "наибольшее, `len(set(a))` показывает, сколько повторов.",
            "**Шаг 2.** Условие из этой задачи: " + self._describe(meta["condition"]) + ".",
            "**Шаг 3.** Один проход по файлу:\n\n```python\n" + self._reference_code(meta) + "```",
            f"**Ответ:** **{answer}** строк. Обратите внимание: спрашивают "
            "**количество строк**, а не номер строки.",
        ]


register(Task09())
