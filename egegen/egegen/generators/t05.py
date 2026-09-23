"""Task 5 — executing an algorithm over the binary (or ternary) representation.

The algorithm is described as a short list of steps in a tiny DSL; the question asks
for the smallest/largest N with a given property of the result. Both solvers apply
the same steps but through different machinery: the fast one works on integers with
bit arithmetic, the naive one manipulates the digit string.
"""

from __future__ import annotations

from typing import Any

from egegen.core.errors import GenerationFailedError
from egegen.core.generator import Generator
from egegen.core.registry import register
from egegen.core.rng import Rng
from egegen.core.templates import render
from egegen.core.types import Instance, Uniqueness
from egegen.solvers.numbers import to_base

SEARCH_LIMIT = 10_000

STEP_LABELS: dict[str, str] = {
    "append_parity_even": (
        "Если сумма цифр полученной записи чётна, к записи справа дописывается 0, "
        "иначе справа дописывается 1."
    ),
    "append_parity_odd": (
        "Если сумма цифр полученной записи нечётна, к записи справа дописывается 0, "
        "иначе справа дописывается 1."
    ),
    "append_last": "К записи справа дописывается её последняя цифра.",
    "append_first": "К записи справа дописывается её первая цифра.",
    "reverse": "Запись переворачивается (читается справа налево).",
    "drop_last": "Последняя цифра записи удаляется.",
    "append_zero": "К записи справа дописывается 0.",
}


class Task05(Generator):
    task_no = 5
    answer_kind = "int"
    checker = "exact"
    uniqueness = Uniqueness.ENUMERATED

    def build(self, rng: Rng, difficulty: int, subtype: str) -> Instance:
        for _ in range(80):
            candidate = self._attempt(rng, difficulty, subtype)
            if candidate is not None:
                return candidate
            rng = rng.fork("retry")
        raise GenerationFailedError(f"t05/{subtype}: no valid instance")

    def _attempt(self, rng: Rng, difficulty: int, subtype: str) -> Instance | None:
        base = 3 if subtype == "5.6_ternary" else 2
        n_steps = 2 if difficulty <= 2 else (3 if difficulty <= 4 else 4)
        steps = self._random_steps(rng, n_steps, base)
        threshold = rng.choice([50, 64, 100, 128, 200, 256, 300, 400, 512, 700, 1000])

        meta: dict[str, Any] = {
            "subtype": subtype,
            "base": base,
            "steps": steps,
            "threshold": threshold,
            # "Which value is unreachable" needs the whole reachable set, so it sweeps
            # twice; a 3000 ceiling keeps that inside the 200 ms generation budget and
            # still covers the range the exam uses.
            "limit": 3000 if subtype == "5.4_unreachable" else SEARCH_LIMIT,
        }
        fields: dict[str, Any] = {
            "steps": self._describe(steps, base),
            "threshold": threshold,
            "base": base,
            "example": "",
        }

        match subtype:
            case "5.1_min_greater":
                meta["question"] = "min_greater"
            case "5.2_max_less":
                meta["question"] = "max_less"
            case "5.3_by_result":
                probe = self._pick_reachable(rng, meta)
                if probe is None:
                    return None
                meta["question"] = "by_result"
                meta["target"] = probe
                fields["target"] = probe
            case "5.4_unreachable":
                options = self._unreachable_options(rng, meta)
                if options is None:
                    return None
                meta["question"] = "unreachable"
                meta["options"] = options
                fields["options"] = ", ".join(str(o) for o in options)
            case "5.5_digit_sum":
                target = rng.randint(3, 6)
                meta["question"] = "digit_sum"
                meta["digit_sum_target"] = target
                fields["digit_sum"] = target
            case "5.6_ternary":
                meta["question"] = "min_greater"
            case _:
                return None

        example = self._example(meta, rng)
        if example is None:
            return None
        fields["example"] = example

        answer = self.solve_fast(meta)
        if answer == "":
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
            template_id=template.id,
            meta=meta,
        )

    def _random_steps(self, rng: Rng, count: int, base: int) -> list[str]:
        pool = ["append_parity_even", "append_parity_odd", "append_last", "reverse"]
        if base == 2:
            pool.append("append_first")
        steps = [rng.choice(pool) for _ in range(count)]
        # Two reverses in a row cancel out, which would make the statement misleading.
        kept = [
            step
            for i, step in enumerate(steps)
            if not (step == "reverse" and i and steps[i - 1] == "reverse")
        ]
        return kept or ["append_parity_even"]

    def _describe(self, steps: list[str], base: int) -> str:
        naming = "двоичной" if base == 2 else "троичной"
        lines = [f"1. Строится {naming} запись числа N (без ведущих нулей)."]
        lines += [f"{i + 2}. {STEP_LABELS[s]}" for i, s in enumerate(steps)]
        lines.append(f"{len(steps) + 2}. Результат переводится в десятичную систему — это R.")
        return "\n".join(lines)

    def _example(self, meta: dict[str, Any], rng: Rng) -> str | None:
        """A worked example, as the exam always provides one."""
        n = rng.randint(4, 30)
        digits = to_base(n, meta["base"])
        result = self._apply_int(n, meta)
        if result is None:
            return None
        final = to_base(result, meta["base"])
        return (
            f"Например, для N = {n} запись — {digits}, после выполнения алгоритма "
            f"получается {final}, то есть R = {result}."
        )

    def _pick_reachable(self, rng: Rng, meta: dict[str, Any]) -> int | None:
        """A result value reached by exactly one N, so the reverse question is well-posed."""
        seen: dict[int, list[int]] = {}
        for n in range(1, 400):
            r = self._apply_int(n, meta)
            if r is not None:
                seen.setdefault(r, []).append(n)
        unique = sorted(r for r, ns in seen.items() if len(ns) == 1 and r > 40)
        return rng.choice(unique) if unique else None

    def _unreachable_options(self, rng: Rng, meta: dict[str, Any]) -> list[int] | None:
        """Four candidates of which exactly one is not a possible result."""
        reachable = sorted(
            {r for n in range(1, meta["limit"]) if (r := self._apply_int(n, meta)) is not None}
        )
        window = [r for r in reachable if 50 <= r <= 5000]
        if len(window) < 3:
            return None
        good = rng.sample(window, 3)
        lo, hi = min(good), max(good)
        misses = [x for x in range(lo, hi + 1) if x not in set(reachable)]
        if not misses:
            return None
        options = sorted([*good, rng.choice(misses)])
        return options

    # -- solving ------------------------------------------------------------
    def _apply_int(self, n: int, meta: dict[str, Any]) -> int | None:
        """Run the algorithm with integer arithmetic — no string handling at all."""
        base: int = meta["base"]
        value = n
        length = max(1, value.bit_length() if base == 2 else len(to_base(value, base)))
        for step in meta["steps"]:
            match step:
                case "append_parity_even" | "append_parity_odd":
                    total = self._digit_sum_int(value, base)
                    even = total % 2 == 0
                    want_even = step == "append_parity_even"
                    digit = 0 if (even == want_even) else 1
                    value = value * base + digit
                    length += 1
                case "append_last":
                    value = value * base + value % base
                    length += 1
                case "append_first":
                    top = value
                    while top >= base:
                        top //= base
                    value = value * base + top
                    length += 1
                case "reverse":
                    reversed_value = 0
                    rest, count = value, 0
                    while rest:
                        reversed_value = reversed_value * base + rest % base
                        rest //= base
                        count += 1
                    value = reversed_value
                    length = count
                case "drop_last":
                    value //= base
                    length -= 1
                case "append_zero":
                    value *= base
                    length += 1
            if value == 0 or length > 40:
                return None
        return value

    def _digit_sum_int(self, value: int, base: int) -> int:
        if base == 2:
            return value.bit_count()
        total = 0
        while value:
            total += value % base
            value //= base
        return total

    def _apply_str(self, n: int, meta: dict[str, Any]) -> int | None:
        """Run the same algorithm on the digit string — the independent check."""
        base: int = meta["base"]
        digits = to_base(n, base)
        for step in meta["steps"]:
            match step:
                case "append_parity_even" | "append_parity_odd":
                    total = sum(int(ch) for ch in digits)
                    even = total % 2 == 0
                    want_even = step == "append_parity_even"
                    digits += "0" if (even == want_even) else "1"
                case "append_last":
                    digits += digits[-1]
                case "append_first":
                    digits += digits[0]
                case "reverse":
                    digits = digits[::-1].lstrip("0") or "0"
                case "drop_last":
                    digits = digits[:-1] or "0"
                case "append_zero":
                    digits += "0"
            if digits == "0" or len(digits) > 40:
                return None
        return int(digits, base)

    def solve_fast(self, meta: dict[str, Any]) -> str:
        return self._answer(meta, self._apply_int)

    def solve_naive(self, meta: dict[str, Any]) -> str | None:
        answer = self._answer(meta, self._apply_str)
        return answer or None

    def _answer(self, meta: dict[str, Any], run: Any) -> str:
        question = meta["question"]
        limit: int = meta["limit"]
        if question == "unreachable":
            options: list[int] = meta["options"]
            reachable = {r for n in range(1, limit) if (r := run(n, meta)) is not None}
            missing = [o for o in options if o not in reachable]
            return str(missing[0]) if len(missing) == 1 else ""
        if question == "by_result":
            hits = [n for n in range(1, 400) if run(n, meta) == meta["target"]]
            return str(hits[0]) if len(hits) == 1 else ""
        threshold: int = meta["threshold"]
        if question == "min_greater":
            for n in range(1, limit):
                r = run(n, meta)
                if r is not None and r > threshold:
                    return str(n)
            return ""
        if question == "max_less":
            best = ""
            for n in range(1, limit):
                r = run(n, meta)
                if r is not None and r < threshold:
                    best = str(n)
            return best
        if question == "digit_sum":
            target: int = meta["digit_sum_target"]
            for n in range(1, limit):
                r = run(n, meta)
                if r is not None and self._digit_sum_int(r, meta["base"]) == target:
                    return str(n)
            return ""
        raise ValueError(question)

    def enumerate_answers(self, meta: dict[str, Any]) -> list[str] | None:
        """For the extremum questions, confirm the extremum is attained by one N."""
        question = meta["question"]
        if question == "unreachable":
            reachable = {
                r for n in range(1, meta["limit"]) if (r := self._apply_int(n, meta)) is not None
            }
            return [str(o) for o in meta["options"] if o not in reachable]
        if question == "by_result":
            return [str(n) for n in range(1, 400) if self._apply_int(n, meta) == meta["target"]]
        answer = self.solve_fast(meta)
        return [answer] if answer else []

    def validate_answer(self, answer: str, meta: dict[str, Any]) -> None:
        if not answer or int(answer) < 1:
            raise ValueError("t05: no N satisfies the condition")

    # -- explanation --------------------------------------------------------
    def _solution(self, meta: dict[str, Any], answer: str) -> list[str]:
        base = meta["base"]
        body = self._python_listing(meta)
        question_line = {
            "min_greater": f"наименьшее N, при котором R > {meta['threshold']}",
            "max_less": f"наибольшее N, при котором R < {meta['threshold']}",
            "by_result": f"N, при котором R = {meta.get('target')}",
            "unreachable": "значение, которое не может быть результатом",
            "digit_sum": (
                "наименьшее N, у результата которого сумма цифр равна "
                f"{meta.get('digit_sum_target')}"
            ),
        }[meta["question"]]
        result = self._apply_int(int(answer), meta) if meta["question"] != "unreachable" else None
        steps = [
            "**Шаг 1.** Не считайте вручную — запишите алгоритм как функцию и "
            "проверьте её на примере из условия:\n\n```python\n" + body + "\n```",
            f"**Шаг 2.** Нужно найти {question_line}. Перебираем N по возрастанию "
            f"и применяем функцию; основание системы счисления — {base}.",
        ]
        if result is not None:
            steps.append(
                f"**Шаг 3.** Подходит N = **{answer}** (при нём R = {result}). "
                "Не перепутайте N и R: в ответе именно N."
            )
        else:
            steps.append(
                f"**Шаг 3.** Перебираем не N, а варианты ответа: недостижимым "
                f"оказывается **{answer}**."
            )
        return steps

    def _python_listing(self, meta: dict[str, Any]) -> str:
        base = meta["base"]
        convert = "bin(n)[2:]" if base == 2 else "to_base(n, 3)"
        lines = ["def f(n):", f"    s = {convert}"]
        for step in meta["steps"]:
            match step:
                case "append_parity_even":
                    lines.append("    s += '0' if sum(map(int, s)) % 2 == 0 else '1'")
                case "append_parity_odd":
                    lines.append("    s += '0' if sum(map(int, s)) % 2 == 1 else '1'")
                case "append_last":
                    lines.append("    s += s[-1]")
                case "append_first":
                    lines.append("    s += s[0]")
                case "reverse":
                    lines.append("    s = s[::-1].lstrip('0') or '0'")
                case "drop_last":
                    lines.append("    s = s[:-1] or '0'")
                case "append_zero":
                    lines.append("    s += '0'")
        lines.append(f"    return int(s, {base})")
        return "\n".join(lines)


register(Task05())
