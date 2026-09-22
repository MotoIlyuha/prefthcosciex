"""Task 25 — integers with conditions on their divisors or matching a mask.

The answer is a short table of pairs. The fast solver sieves the whole range at
once; the naive one uses the per-number sqrt sweep the method card teaches, so the
two disagree if either the sieve or the sweep mishandles perfect squares.
"""

from __future__ import annotations

from fnmatch import fnmatch
from typing import Any

from egegen.core.errors import GenerationFailed
from egegen.core.generator import Generator
from egegen.core.registry import register
from egegen.core.rng import Rng
from egegen.core.templates import render
from egegen.core.types import Instance, Uniqueness
from egegen.solvers.numbers import divisors


class Task25(Generator):
    task_no = 25
    answer_kind = "pairs_list"
    checker = "custom:pairs_list"
    requires_code = True
    uniqueness = Uniqueness.ENUMERATED
    generation_budget_ms = 400

    def build(self, rng: Rng, difficulty: int, subtype: str) -> Instance:
        for _ in range(60):
            candidate = self._attempt(rng, difficulty, subtype)
            if candidate is not None:
                return candidate
            rng = rng.fork("retry")
        raise GenerationFailed(f"t25/{subtype}: no instance with 1..8 answer pairs")

    def _attempt(self, rng: Rng, difficulty: int, subtype: str) -> Instance | None:
        meta: dict[str, Any] = {"subtype": subtype}
        fields: dict[str, Any] = {}

        match subtype:
            case "25.1_divisor_count":
                picked = self._range_with_k(rng, 1200, 2600, 1, 8)
                if picked is None:
                    return None
                lo, hi, k = picked
                meta.update({"question": "divisor_count", "lo": lo, "hi": hi, "k": k})
                fields.update({"lo": lo, "hi": hi, "k": k})
            case "25.2_mask_multiple":
                multiplier = rng.choice([143, 187, 209, 323, 391, 437, 1023, 2047])
                mask = self._mask_from_multiple(rng, multiplier, difficulty)
                meta.update(
                    {
                        "question": "mask",
                        "multiplier": multiplier,
                        "mask": mask,
                        "lo": 10**6,
                        "hi": 10**7,
                    }
                )
                fields.update({"multiplier": multiplier, "mask": mask})
            case "25.3_largest_proper":
                picked = self._range_with_k(rng, 1200, 2600, 1, 8)
                if picked is None:
                    return None
                lo, hi, k = picked
                meta.update({"question": "largest_proper", "lo": lo, "hi": hi, "k": k})
                fields.update({"lo": lo, "hi": hi, "k": k})
            case "25.4_divisor_sum":
                picked = self._range_with_k(rng, 1200, 2600, 1, 8)
                if picked is None:
                    return None
                lo, hi, k = picked
                meta.update({"question": "divisor_sum", "lo": lo, "hi": hi, "k": k})
                fields.update({"lo": lo, "hi": hi, "k": k})
            case "25.5_count_only":
                picked = self._range_with_k(rng, 3000, 6000, 3, 60)
                if picked is None:
                    return None
                lo, hi, k = picked
                meta.update({"question": "count_only", "lo": lo, "hi": hi, "k": k})
                fields.update({"lo": lo, "hi": hi, "k": k})
            case _:
                return None

        pairs = self._find(meta)
        if meta["question"] == "count_only":
            answer = str(len(pairs))
            if not 3 <= len(pairs) <= 60:
                return None
            answer_kind, checker = "int", "exact"
        else:
            if not 1 <= len(pairs) <= 8:
                return None
            answer = ", ".join(f"{a} {b}" for a, b in pairs)
            answer_kind, checker = "pairs_list", "custom:pairs_list"

        template = self.templates.pick(rng, subtype)
        return Instance(
            task_no=self.task_no,
            subtype=subtype,
            difficulty=difficulty,
            seed=0,
            statement_md=render(template, **fields),
            answer=answer,
            answer_kind=answer_kind,
            checker=checker,
            solution_steps=self._solution(meta, pairs, answer),
            reference_code=self._reference_code(meta),
            template_id=template.id,
            uniqueness=Uniqueness.ENUMERATED,
            meta=meta,
        )

    def _mask_from_multiple(self, rng: Rng, multiplier: int, difficulty: int) -> str:
        """A mask like ``1?2*3``, built by blanking digits of a real multiple.

        Drawing the mask at random almost always yields zero or dozens of hits;
        deriving it from an actual multiple guarantees at least one and keeps the
        answer table short.
        """
        count = 10**7 // multiplier
        digits = list(str(rng.randint(count // 4, count) * multiplier))
        holes = 1 if difficulty <= 2 else 2
        positions = rng.sample(range(1, len(digits) - 1), min(holes, len(digits) - 2))
        for pos in positions:
            digits[pos] = "?"
        if difficulty >= 3:
            start = rng.randint(2, len(digits) - 3)
            span = rng.randint(1, 2)
            digits[start : start + span] = ["*"]
        return "".join(digits)

    def _range_with_k(
        self, rng: Rng, min_width: int, max_width: int, lo_hits: int, hi_hits: int
    ) -> tuple[int, int, int] | None:
        """Pick a range and a divisor count that together give the wanted hit count.

        The sieve runs once and the divisor count is chosen from its histogram, so a
        usable instance is found in a single pass rather than by re-rolling the range
        and re-sieving each time.
        """
        lo = rng.randint(20_000, 400_000)
        hi = lo + rng.randint(min_width, max_width)
        counts = self._divisor_counts(lo, hi)
        histogram: dict[int, int] = {}
        for total in counts.values():
            histogram[total] = histogram.get(total, 0) + 1
        usable = sorted(k for k, n in histogram.items() if lo_hits <= n <= hi_hits and k >= 3)
        if not usable:
            return None
        return lo, hi, rng.choice(usable)

    # -- solving ------------------------------------------------------------
    def _divisor_counts(self, lo: int, hi: int) -> dict[int, int]:
        """Sieve the divisor count for every number in the range at once."""
        counts = dict.fromkeys(range(lo, hi + 1), 0)
        for d in range(1, hi + 1):
            if d * d > hi:
                break
            start = max(d * d, ((lo + d - 1) // d) * d)
            for multiple in range(start, hi + 1, d):
                other = multiple // d
                if other < d:
                    continue
                counts[multiple] += 1 if other == d else 2
        return counts

    def _find(self, meta: dict[str, Any]) -> list[tuple[int, int]]:
        match meta["question"]:
            case "mask":
                m, mask = meta["multiplier"], meta["mask"]
                return [
                    (x, x // m)
                    for x in range(((meta["lo"] + m - 1) // m) * m, meta["hi"] + 1, m)
                    if fnmatch(str(x), mask)
                ]
            case "divisor_count" | "count_only":
                counts = self._divisor_counts(meta["lo"], meta["hi"])
                out: list[tuple[int, int]] = []
                for n, total in counts.items():
                    if total == meta["k"]:
                        ds = divisors(n)
                        out.append((n, ds[-2]))
                return sorted(out)
            case "largest_proper":
                counts = self._divisor_counts(meta["lo"], meta["hi"])
                return sorted(
                    (n, divisors(n)[-2]) for n, total in counts.items() if total == meta["k"]
                )
            case "divisor_sum":
                counts = self._divisor_counts(meta["lo"], meta["hi"])
                return sorted(
                    (n, sum(divisors(n)))
                    for n, total in counts.items()
                    if total == meta["k"]
                )
        raise ValueError(meta["question"])

    def _find_naive(self, meta: dict[str, Any]) -> list[tuple[int, int]]:
        """Per-number sweep, the way the method card teaches it."""
        match meta["question"]:
            case "mask":
                m, mask = meta["multiplier"], meta["mask"]
                return [
                    (x, x // m)
                    for x in range(meta["lo"], meta["hi"] + 1)
                    if x % m == 0 and fnmatch(str(x), mask)
                ]
            case _:
                out: list[tuple[int, int]] = []
                for n in range(meta["lo"], meta["hi"] + 1):
                    ds = divisors(n)
                    if len(ds) != meta["k"]:
                        continue
                    second = (
                        sum(ds) if meta["question"] == "divisor_sum" else ds[-2]
                    )
                    out.append((n, second))
                return sorted(out)

    def solve_fast(self, meta: dict[str, Any]) -> str:
        pairs = self._find(meta)
        if meta["question"] == "count_only":
            return str(len(pairs))
        return ", ".join(f"{a} {b}" for a, b in pairs)

    def solve_naive(self, meta: dict[str, Any]) -> str | None:
        if meta["question"] == "mask" and meta["hi"] - meta["lo"] > 200_000:
            return None  # scanning 10^7 numbers one by one is not a check, it is a hang
        pairs = self._find_naive(meta)
        if meta["question"] == "count_only":
            return str(len(pairs))
        return ", ".join(f"{a} {b}" for a, b in pairs)

    def enumerate_answers(self, meta: dict[str, Any]) -> list[str] | None:
        """For the mask variant, re-derive the hits by a regex instead of fnmatch."""
        if meta["question"] != "mask":
            return [self.solve_fast(meta)]
        import re

        pattern = re.compile(
            "^" + meta["mask"].replace("?", "[0-9]").replace("*", "[0-9]*") + "$"
        )
        m = meta["multiplier"]
        pairs = [
            (x, x // m)
            for x in range(((meta["lo"] + m - 1) // m) * m, meta["hi"] + 1, m)
            if pattern.match(str(x))
        ]
        return [", ".join(f"{a} {b}" for a, b in pairs)]

    def validate_answer(self, answer: str, meta: dict[str, Any]) -> None:
        if not answer:
            raise ValueError("t25: no numbers satisfy the condition")

    # -- explanation --------------------------------------------------------
    def _reference_code(self, meta: dict[str, Any]) -> str:
        if meta["question"] == "mask":
            return (
                "from fnmatch import fnmatch\n"
                f"M = {meta['multiplier']}\n"
                f"for x in range(M, {meta['hi']} + 1, M):   # только кратные M\n"
                f"    if fnmatch(str(x), '{meta['mask']}'):\n"
                "        print(x, x // M)\n"
            )
        second = {
            "divisor_count": "ds[-2]",
            "largest_proper": "ds[-2]",
            "divisor_sum": "sum(ds)",
            "count_only": "ds[-2]",
        }[meta["question"]]
        head = "cnt = 0\n" if meta["question"] == "count_only" else ""
        body = "        cnt += 1\n" if meta["question"] == "count_only" else (
            f"        print(n, {second})\n"
        )
        return (
            "def divisors(n):\n"
            "    ds = set()\n"
            "    for d in range(1, int(n ** 0.5) + 1):\n"
            "        if n % d == 0: ds.add(d); ds.add(n // d)\n"
            "    return sorted(ds)\n\n"
            + head
            + f"for n in range({meta['lo']}, {meta['hi']} + 1):\n"
            "    ds = divisors(n)\n"
            f"    if len(ds) == {meta['k']}:\n"
            + body
            + ("print(cnt)\n" if meta["question"] == "count_only" else "")
        )

    def _solution(
        self, meta: dict[str, Any], pairs: list[tuple[int, int]], answer: str
    ) -> list[str]:
        if meta["question"] == "mask":
            return [
                "**Шаг 1.** Перебирать все числа до 10⁷ бессмысленно — перебирайте "
                f"только **кратные {meta['multiplier']}**: "
                f"`range(M, N, M)`. Их в тысячи раз меньше.",
                "**Шаг 2.** Маску проверяет `fnmatch` из стандартной библиотеки: "
                "`?` — ровно один символ, `*` — любое количество символов, в том "
                "числе ноль.\n\n```python\n" + self._reference_code(meta) + "```",
                f"**Шаг 3.** Найденные пары (число и частное), по возрастанию "
                f"числа: **{answer}**.",
            ]
        return [
            "**Шаг 1.** Делители ищем перебором до квадратного корня: для каждого "
            "d от 1 до √n, если n делится на d, добавляем в множество **и d, "
            "и n // d**. Множество само уберёт дубликат у полного квадрата.",
            "**Шаг 2.** Перебираем числа диапазона и отбираем нужные:\n\n```python\n"
            + self._reference_code(meta)
            + "```",
            (
                f"**Шаг 3.** Подходящих чисел {len(pairs)}, ответ — **{answer}**."
                if meta["question"] != "count_only"
                else f"**Шаг 3.** Подходящих чисел **{answer}**."
            )
            + " Если пар получилось около сотни — условие прочитано неверно.",
        ]


register(Task25())
