"""Task 26 — sorting and greedy algorithms over a file (2 points).

Two numbers are asked for, and the second is the one students lose: it is not the
last item the greedy loop took, but the largest item that could appear in *some*
optimal set. The fast solver answers it with prefix sums and a binary search; at
difficulty 1 the instance is small enough for the naive solver to check every
subset outright.
"""

from __future__ import annotations

import bisect
from itertools import combinations
from typing import Any

from egegen.core.errors import GenerationFailed
from egegen.core.generator import Generator
from egegen.core.registry import register
from egegen.core.rng import Rng
from egegen.core.tables import to_txt
from egegen.core.templates import render
from egegen.core.types import Attachment, Instance, Uniqueness

BRUTE_LIMIT = 18


class Task26(Generator):
    task_no = 26
    answer_kind = "two_ints"
    checker = "int_pair_ordered"
    requires_code = True
    uniqueness = Uniqueness.FUNCTIONAL
    generation_budget_ms = 600
    sweep_seeds = 12

    def build(self, rng: Rng, difficulty: int, subtype: str) -> Instance:
        for _ in range(30):
            candidate = self._attempt(rng, difficulty, subtype)
            if candidate is not None:
                return candidate
            rng = rng.fork("retry")
        raise GenerationFailed(f"t26/{subtype}: no valid instance")

    def _attempt(self, rng: Rng, difficulty: int, subtype: str) -> Instance | None:
        # Difficulty 1 keeps the dataset small enough to check by exhaustive search;
        # from 2 upward it is exam sized and the cross-check is the second algorithm.
        size = rng.randint(10, BRUTE_LIMIT) if difficulty == 1 else rng.randint(
            1000, 20_000 * min(difficulty, 4)
        )
        scenario = self._scenario(subtype)
        values = [rng.randint(scenario["min"], scenario["max"]) for _ in range(size)]
        capacity = self._capacity(rng, values, difficulty)
        if capacity is None:
            return None

        meta: dict[str, Any] = {
            "subtype": subtype,
            "question": scenario["question"],
            "values": values,
            "capacity": capacity,
            "size": size,
        }
        count, best = self._solve_prefix(meta)
        if count < 2 or count >= size:
            return None
        answer = f"{count} {best}"

        header = f"{size} {capacity}"
        payload = to_txt([header, *values])
        template = self.templates.pick(rng, subtype)
        return Instance(
            task_no=self.task_no,
            subtype=subtype,
            difficulty=difficulty,
            seed=0,
            statement_md=render(
                template,
                size=size,
                capacity=capacity,
                unit=scenario["unit"],
                item=scenario["item"],
                preview="\n".join([header, *[str(v) for v in values[:8]]]),
            ),
            answer=answer,
            solution_steps=self._solution(meta, count, best),
            reference_code=self._reference_code(meta),
            template_id=template.id,
            assets=[Attachment("26.txt", "text/plain", "txt", payload)],
            meta=meta,
        )

    def _scenario(self, subtype: str) -> dict[str, Any]:
        return {
            "26.1_files_on_disk": {
                "question": "max_count",
                "item": "файлов",
                "unit": "Кбайт",
                "min": 10,
                "max": 5000,
            },
            "26.2_boxes": {
                "question": "max_count",
                "item": "коробок",
                "unit": "кг",
                "min": 1,
                "max": 300,
            },
            "26.3_passengers": {
                "question": "max_count",
                "item": "групп",
                "unit": "мест",
                "min": 1,
                "max": 60,
            },
            "26.4_min_removed": {
                "question": "min_total",
                "item": "деталей",
                "unit": "г",
                "min": 5,
                "max": 900,
            },
            "26.5_two_containers": {
                "question": "two_containers",
                "item": "грузов",
                "unit": "кг",
                "min": 5,
                "max": 400,
            },
        }[subtype]

    def _capacity(self, rng: Rng, values: list[int], difficulty: int) -> int | None:
        """A capacity that admits a strict subset — never all items, never almost none."""
        total = sum(values)
        share = rng.randint(25, 70) / 100
        capacity = int(total * share)
        return capacity if capacity >= max(values) else None

    # -- solving ------------------------------------------------------------
    def _solve_prefix(self, meta: dict[str, Any]) -> tuple[int, int]:
        """Greedy count, then the largest admissible item via prefix sums + bisect."""
        values = sorted(meta["values"])
        capacity = meta["capacity"]
        prefix = [0]
        for v in values:
            prefix.append(prefix[-1] + v)

        count = 0
        while count < len(values) and prefix[count + 1] <= capacity:
            count += 1

        if meta["question"] == "min_total":
            # The lightest possible set of `count` items is the `count` smallest ones,
            # so its total is the prefix sum — well defined, unlike "what is left
            # over", which depends on which optimal set you happen to pick.
            return count, prefix[count]
        if meta["question"] == "two_containers":
            # Fill a second container with what is left over, same greedy rule.
            rest = values[count:]
            second = 0
            running = 0
            for v in rest:
                if running + v > capacity:
                    break
                running += v
                second += 1
            return count, second

        # The largest item that can belong to *some* set of `count` items: keep the
        # cheapest count-1 items and see how large the remaining slot may be.
        room = capacity - prefix[count - 1]
        index = bisect.bisect_right(values, room) - 1
        best = max(values[count - 1], values[index] if index >= 0 else 0)
        return count, best

    def _solve_bruteforce(self, meta: dict[str, Any]) -> tuple[int, int] | None:
        """Every subset, for the small instances at difficulty 1."""
        values = sorted(meta["values"])
        if len(values) > BRUTE_LIMIT:
            return None
        capacity = meta["capacity"]
        best_count = 0
        for size in range(len(values), 0, -1):
            if any(sum(c) <= capacity for c in combinations(values, size)):
                best_count = size
                break
        if meta["question"] == "min_total":
            return best_count, min(
                sum(c) for c in combinations(values, best_count) if sum(c) <= capacity
            )
        if meta["question"] == "two_containers":
            return None  # the second container follows the stated greedy rule only
        best_item = max(
            max(c)
            for c in combinations(values, best_count)
            if sum(c) <= capacity
        )
        return best_count, best_item

    def solve_fast(self, meta: dict[str, Any]) -> str:
        count, best = self._solve_prefix(meta)
        return f"{count} {best}"

    def solve_naive(self, meta: dict[str, Any]) -> str | None:
        result = self._solve_bruteforce(meta)
        return None if result is None else f"{result[0]} {result[1]}"

    def enumerate_answers(self, meta: dict[str, Any]) -> list[str] | None:
        """Second, independent derivation for the exam-sized instances."""
        if len(meta["values"]) <= BRUTE_LIMIT and meta["question"] != "two_containers":
            return None  # solve_naive already checked this one exhaustively
        values = sorted(meta["values"])
        capacity = meta["capacity"]
        prefix = [0]
        for v in values:
            prefix.append(prefix[-1] + v)
        # Binary search for the count instead of walking the prefix sums.
        lo, hi = 0, len(values)
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if prefix[mid] <= capacity:
                lo = mid
            else:
                hi = mid - 1
        count = lo
        if meta["question"] == "min_total":
            return [f"{count} {prefix[count]}"]
        if meta["question"] == "two_containers":
            rest = values[count:]
            running = second = 0
            for v in rest:
                if running + v > capacity:
                    break
                running += v
                second += 1
            return [f"{count} {second}"]
        # Linear scan for the largest admissible item, no bisect involved.
        room = capacity - prefix[count - 1]
        best = values[count - 1]
        for v in values:
            if v <= room and v > best:
                best = v
        return [f"{count} {best}"]

    def validate_answer(self, answer: str, meta: dict[str, Any]) -> None:
        count = int(answer.split()[0])
        if count < 1:
            raise ValueError("t26: the greedy set is empty")

    # -- explanation --------------------------------------------------------
    def _reference_code(self, meta: dict[str, Any]) -> str:
        head = (
            "import bisect\n"
            "f = open('26.txt')\n"
            "n, S = map(int, f.readline().split())      # первая строка — параметры\n"
            "a = sorted(int(f.readline()) for _ in range(n))\n"
            "total = cnt = 0\n"
            "for x in a:\n"
            "    if total + x <= S: total += x; cnt += 1\n"
            "    else: break\n"
        )
        match meta["question"]:
            case "min_total":
                return head + "print(cnt, total)\n"
            case "two_containers":
                return head + (
                    "rest = a[cnt:]\nrunning = second = 0\n"
                    "for x in rest:\n"
                    "    if running + x > S: break\n"
                    "    running += x; second += 1\n"
                    "print(cnt, second)\n"
                )
        return head + (
            "free = S - (total - a[cnt - 1])            # убираем последний взятый\n"
            "j = bisect.bisect_right(a, free) - 1       # самый большой, который влезет\n"
            "print(cnt, max(a[cnt - 1], a[j]))\n"
        )

    def _solution(self, meta: dict[str, Any], count: int, best: int) -> list[str]:
        common = [
            "**Шаг 1.** Первая строка файла — **параметры**, а не данные. Читаем её "
            "отдельно: `n, S = map(int, f.readline().split())`.",
            "**Шаг 2.** Чтобы взять как можно больше элементов, берём самые "
            "маленькие: сортируем и набираем, пока помещается. Так получается "
            f"первое число ответа — **{count}**.",
        ]
        match meta["question"]:
            case "min_total":
                common.append(
                    "**Шаг 3.** Второе число — наименьшая возможная суммарная масса "
                    f"такого набора. Это ровно сумма {count} самых лёгких деталей: "
                    f"**{best}**."
                )
            case "two_containers":
                common.append(
                    "**Шаг 3.** Оставшиеся элементы складываем во второй контейнер "
                    f"по тому же правилу: туда помещается **{best}**."
                )
            case _:
                common.append(
                    "**Шаг 3.** Второе число — это **не** последний взятый элемент. "
                    "Спрашивают наибольший элемент, который может оказаться в наборе "
                    f"из {count} штук. Уберём последний взятый, посмотрим, сколько "
                    "места освободилось, и найдём самый большой элемент, который туда "
                    f"влезет:\n\n```python\n{self._reference_code(meta)}```\n\n"
                    f"Получаем **{best}**."
                )
        common.append(
            f"**Ответ:** **{count} {best}** — два числа через пробел, в указанном "
            "порядке. За одно верное число даётся 1 балл из 2."
        )
        return common


register(Task26())
