"""Task 17 — processing a sequence of integers from a file.

The answer is two numbers: how many neighbouring groups satisfy the condition, and
the largest sum among them. The fast solver makes one indexed pass; the naive one
builds the qualifying groups as a list and asks ``len`` and ``max`` separately, so an
off-by-one in the window logic cannot survive both.
"""

from __future__ import annotations

from typing import Any

from egegen.core.errors import GenerationFailedError
from egegen.core.generator import Generator
from egegen.core.registry import register
from egegen.core.rng import Rng
from egegen.core.tables import to_txt
from egegen.core.templates import render
from egegen.core.types import Attachment, Instance, Uniqueness

LOW, HIGH = -10_000, 10_000


class Task17(Generator):
    task_no = 17
    answer_kind = "two_ints"
    checker = "int_pair_ordered"
    requires_code = True
    uniqueness = Uniqueness.FUNCTIONAL
    generation_budget_ms = 400

    def build(self, rng: Rng, difficulty: int, subtype: str) -> Instance:
        for _ in range(25):
            candidate = self._attempt(rng, difficulty, subtype)
            if candidate is not None:
                return candidate
            rng = rng.fork("retry")
        raise GenerationFailedError(f"t17/{subtype}: no instance with a usable count")

    def _attempt(self, rng: Rng, difficulty: int, subtype: str) -> Instance | None:
        size = 5000 + rng.randint(0, 3) * 1000
        numbers = [rng.randint(LOW, HIGH) for _ in range(size)]
        condition = self._condition(rng, difficulty, subtype)
        if condition is None:
            return None

        meta: dict[str, Any] = {
            "subtype": subtype,
            "numbers": numbers,
            "condition": condition,
            "size": size,
        }
        count, best = self._scan_indexed(meta)
        # The doc calls for 5..500 hits: fewer and the maximum is luck, more and the
        # task stops discriminating.
        if not 5 <= count <= 500:
            return None
        answer = f"{count} {best}"

        template = self.templates.pick(rng, subtype)
        statement = render(
            template,
            size=size,
            condition=self._describe(condition),
            preview="\n".join(str(x) for x in numbers[:10]),
            span=condition.get("span", 2),
            gap=condition.get("gap", 1),
        )
        return Instance(
            task_no=self.task_no,
            subtype=subtype,
            difficulty=difficulty,
            seed=0,
            statement_md=statement,
            answer=answer,
            solution_steps=self._solution(meta, count, best),
            reference_code=self._reference_code(meta),
            template_id=template.id,
            assets=[
                Attachment("17.txt", "text/plain", "txt", to_txt(numbers)),
            ],
            meta=meta,
        )

    def _condition(self, rng: Rng, difficulty: int, subtype: str) -> dict[str, Any] | None:
        # Divisors are chosen so the hit count lands in the 5..500 band the doc asks
        # for; a smaller divisor would match thousands of groups and stop testing
        # anything but the reading of the file.
        divisor = rng.choice([4, 5, 6, 7, 8, 9, 11])
        other = rng.choice([5, 7, 8, 9, 11])
        match subtype:
            case "17.1_divisible_pair":
                return {
                    "kind": "both_divisible",
                    "divisor": divisor,
                    "span": 2,
                    "gap": 1,
                }
            case "17.2_exactly_one":
                return {
                    "kind": rng.choice(["exactly_one", "at_least_one"]),
                    "divisor": divisor,
                    "sum_divisor": other,
                    "span": 2,
                    "gap": 1,
                }
            case "17.3_global_value":
                return {
                    "kind": "global_reference",
                    "digit": rng.choice([1, 3, 7, 9]),
                    "divisor": rng.choice([3, 4, 5]),
                    "span": 2,
                    "gap": 1,
                }
            case "17.4_triples":
                return {
                    "kind": "triple_sum",
                    "divisor": divisor,
                    "positive": True,
                    "span": 3,
                    "gap": 1,
                }
            case "17.5_distance_k":
                gap = rng.randint(2, 4 + difficulty)
                return {
                    "kind": "distance_pair",
                    "divisor": divisor,
                    "positive": True,
                    "span": 2,
                    "gap": gap,
                }
        return None

    def _describe(self, condition: dict[str, Any]) -> str:
        match condition["kind"]:
            case "both_divisible":
                return f"оба числа пары делятся на {condition['divisor']} без остатка"
            case "exactly_one":
                return (
                    f"**ровно одно** из двух чисел делится на {condition['divisor']}, "
                    f"а их сумма делится на {condition['sum_divisor']}"
                )
            case "at_least_one":
                return (
                    f"**хотя бы одно** из двух чисел делится на {condition['divisor']}, "
                    f"а их сумма делится на {condition['sum_divisor']}"
                )
            case "global_reference":
                return (
                    "сумма пары **больше** наибольшего в файле числа, "
                    f"оканчивающегося на цифру {condition['digit']}, "
                    f"и делится на {condition['divisor']}"
                )
            case "triple_sum":
                return f"все три числа положительны, а их сумма делится на {condition['divisor']}"
            case "distance_pair":
                return f"оба числа положительны, а их сумма делится на {condition['divisor']}"
        raise ValueError(condition["kind"])

    # -- solving ------------------------------------------------------------
    def _threshold(self, numbers: list[int], digit: int) -> int | None:
        """Largest number whose last digit is ``digit``.

        The last digit is taken from ``abs(x)``: in Python ``-7 % 10`` is 3, which is
        exactly the trap this subtype is built around.
        """
        candidates = [x for x in numbers if abs(x) % 10 == digit]
        return max(candidates) if candidates else None

    def _group_ok(self, group: list[int], condition: dict[str, Any], threshold: int | None) -> bool:
        match condition["kind"]:
            case "both_divisible":
                return all(x % condition["divisor"] == 0 for x in group)
            case "exactly_one":
                hits = sum(x % condition["divisor"] == 0 for x in group)
                return hits == 1 and sum(group) % int(condition["sum_divisor"]) == 0
            case "at_least_one":
                hits = sum(x % condition["divisor"] == 0 for x in group)
                return hits >= 1 and sum(group) % int(condition["sum_divisor"]) == 0
            case "global_reference":
                return (
                    threshold is not None
                    and sum(group) > threshold
                    and sum(group) % condition["divisor"] == 0
                )
            case "triple_sum" | "distance_pair":
                if condition.get("positive") and any(x <= 0 for x in group):
                    return False
                return sum(group) % int(condition["divisor"]) == 0
        raise ValueError(condition["kind"])

    def _scan_indexed(self, meta: dict[str, Any]) -> tuple[int, int]:
        """One indexed pass, accumulating the count and the running maximum."""
        numbers: list[int] = meta["numbers"]
        condition = meta["condition"]
        span, gap = condition.get("span", 2), condition.get("gap", 1)
        threshold = (
            self._threshold(numbers, condition["digit"])
            if condition["kind"] == "global_reference"
            else None
        )
        count = 0
        best = -(10**9)
        last = len(numbers) - (gap * (span - 1))
        for i in range(last):
            group = [numbers[i + gap * k] for k in range(span)]
            if self._group_ok(group, condition, threshold):
                count += 1
                total = sum(group)
                if total > best:
                    best = total
        return count, best

    def _scan_listwise(self, meta: dict[str, Any]) -> tuple[int, int]:
        """Collect the qualifying groups first, then ask len() and max() separately."""
        numbers: list[int] = meta["numbers"]
        condition = meta["condition"]
        span, gap = condition.get("span", 2), condition.get("gap", 1)
        threshold = (
            self._threshold(numbers, condition["digit"])
            if condition["kind"] == "global_reference"
            else None
        )
        windows = [
            numbers[i : i + gap * (span - 1) + 1 : gap]
            for i in range(len(numbers) - gap * (span - 1))
        ]
        hits = [w for w in windows if len(w) == span and self._group_ok(w, condition, threshold)]
        return len(hits), max((sum(w) for w in hits), default=-(10**9))

    def solve_fast(self, meta: dict[str, Any]) -> str:
        count, best = self._scan_indexed(meta)
        return f"{count} {best}"

    def solve_naive(self, meta: dict[str, Any]) -> str | None:
        count, best = self._scan_listwise(meta)
        return f"{count} {best}"

    def validate_answer(self, answer: str, meta: dict[str, Any]) -> None:
        count = int(answer.split()[0])
        if not 1 <= count <= 2000:
            raise ValueError(f"t17: implausible count {count}")

    # -- explanation --------------------------------------------------------
    def _reference_code(self, meta: dict[str, Any]) -> str:
        condition = meta["condition"]
        span, gap = condition.get("span", 2), condition.get("gap", 1)
        head = "a = [int(x) for x in open('17.txt')]\n"
        if condition["kind"] == "global_reference":
            head += (
                f"m = max(x for x in a if abs(x) % 10 == {condition['digit']})\n"
                "# abs(...) — потому что у отрицательных чисел % 10 в Python "
                "даёт не ту цифру\n"
            )
        names = ["x", "y", "z"][:span]
        unpack = ", ".join(names)
        take = ", ".join(f"a[i + {gap * k}]" if gap * k else "a[i]" for k in range(span))
        test = {
            "both_divisible": f"{names[0]} % {condition.get('divisor')} == 0 and "
            f"{names[1]} % {condition.get('divisor')} == 0",
            "exactly_one": f"(({names[0]} % {condition.get('divisor')} == 0) != "
            f"({names[1]} % {condition.get('divisor')} == 0)) and "
            f"(x + y) % {condition.get('sum_divisor')} == 0",
            "at_least_one": f"(({names[0]} % {condition.get('divisor')} == 0) or "
            f"({names[1]} % {condition.get('divisor')} == 0)) and "
            f"(x + y) % {condition.get('sum_divisor')} == 0",
            "global_reference": f"x + y > m and (x + y) % {condition.get('divisor')} == 0",
            "triple_sum": f"x > 0 and y > 0 and z > 0 and "
            f"(x + y + z) % {condition.get('divisor')} == 0",
            "distance_pair": f"x > 0 and y > 0 and (x + y) % {condition.get('divisor')} == 0",
        }[condition["kind"]]
        return (
            head
            + "cnt = 0\nbest = -10**9\n"
            + f"for i in range(len(a) - {gap * (span - 1)}):\n"
            + f"    {unpack} = {take}\n"
            + f"    if {test}:\n"
            + f"        cnt += 1\n        best = max(best, {' + '.join(names)})\n"
            + "print(cnt, best)\n"
        )

    def _solution(self, meta: dict[str, Any], count: int, best: int) -> list[str]:
        condition = meta["condition"]
        steps = [
            "**Шаг 1.** Читаем файл в список: `a = [int(x) for x in open('17.txt')]`. "
            "Одна строка — одно число.",
        ]
        if condition["kind"] == "global_reference":
            threshold = self._threshold(meta["numbers"], condition["digit"])
            steps.append(
                "**Шаг 2.** Сначала вычисляем вспомогательную величину — наибольшее "
                f"число, оканчивающееся на {condition['digit']}. Для отрицательных "
                "чисел последнюю цифру берём как `abs(x) % 10`: в Python "
                "`-7 % 10` равно 3, а не 7. Здесь она равна "
                f"**{threshold}**."
            )
        steps.append(
            "**Шаг "
            + ("3" if condition["kind"] == "global_reference" else "2")
            + "."
            + " Один проход по индексам, накапливаем счётчик и максимум:\n\n```python\n"
            + self._reference_code(meta)
            + "```"
        )
        steps.append(
            f"**Ответ:** **{count} {best}** — сначала количество, затем максимальная "
            "сумма. Порядок вывода менять нельзя."
        )
        return steps


register(Task17())
