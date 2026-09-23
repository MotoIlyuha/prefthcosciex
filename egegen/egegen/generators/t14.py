"""Task 14 — positional notation: digits of a large expression in base b.

Python's integers are exact, so the whole task is "compute the value, convert it,
count something". The two solvers convert differently: repeated division against
greedy subtraction of powers.
"""

from __future__ import annotations

from typing import Any

from egegen.core.errors import GenerationFailedError
from egegen.core.generator import Generator
from egegen.core.registry import register
from egegen.core.rng import Rng
from egegen.core.templates import render
from egegen.core.types import Instance, Uniqueness
from egegen.solvers.numbers import DIGITS, to_base


class Task14(Generator):
    task_no = 14
    answer_kind = "int"
    checker = "exact"
    uniqueness = Uniqueness.FUNCTIONAL

    def build(self, rng: Rng, difficulty: int, subtype: str) -> Instance:
        for _ in range(80):
            candidate = self._attempt(rng, difficulty, subtype)
            if candidate is not None:
                return candidate
            rng = rng.fork("retry")
        raise GenerationFailedError(f"t14/{subtype}: no valid instance")

    def _attempt(self, rng: Rng, difficulty: int, subtype: str) -> Instance | None:
        base = rng.choice([3, 4, 5, 6, 7, 8, 9] if difficulty <= 3 else [7, 8, 9, 11, 12, 14, 16])
        meta: dict[str, Any] = {"subtype": subtype, "base": base}
        fields: dict[str, Any] = {"base": base}

        match subtype:
            case "14.1_count_digit" | "14.3_digit_sum":
                terms = self._random_expression(rng, base, difficulty)
                if not self._positive(terms):
                    return None
                digit = rng.randint(0, min(base - 1, 9))
                meta["terms"] = terms
                meta["question"] = "count" if subtype == "14.1_count_digit" else "digit_sum"
                meta["digit"] = digit
                fields["expression"] = self._format_expression(terms)
                fields["digit"] = DIGITS[digit]
            case "14.2_unknown_digit":
                pattern, divisor = self._unknown_digit_problem(rng, base, difficulty)
                if pattern is None:
                    return None
                meta["question"] = "unknown_digit"
                meta["pattern"] = pattern
                meta["divisor"] = divisor
                fields["pattern"] = pattern
                fields["divisor"] = divisor
            case "14.4_min_base":
                terms = self._random_expression(rng, 10, difficulty)
                if not self._positive(terms):
                    return None
                suffix_len = rng.randint(1, 2)
                meta["question"] = "min_base"
                meta["terms"] = terms
                meta["zeros"] = suffix_len
                fields["expression"] = self._format_expression(terms)
                fields["zeros"] = suffix_len
            case "14.5_mixed_bases":
                left_base = rng.choice([3, 5, 7])
                right_base = rng.choice([4, 6, 8])
                left = rng.randint(base**2, base**3)
                right = rng.randint(base**2, base**3)
                meta["question"] = "mixed"
                meta["left"] = to_base(left, left_base)
                meta["left_base"] = left_base
                meta["right"] = to_base(right, right_base)
                meta["right_base"] = right_base
                meta["digit"] = rng.randint(0, min(base - 1, 9))
                fields.update(
                    {
                        "left": meta["left"],
                        "left_base": left_base,
                        "right": meta["right"],
                        "right_base": right_base,
                        "digit": DIGITS[meta["digit"]],
                    }
                )
            case _:
                return None

        answer = self.solve_fast(meta)
        if not answer or not 1 <= int(answer) <= 10**6:
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
            uniqueness=(
                Uniqueness.ENUMERATED
                if meta["question"] in ("unknown_digit", "min_base")
                else Uniqueness.FUNCTIONAL
            ),
            meta=meta,
        )

    def _random_expression(self, rng: Rng, base: int, difficulty: int) -> list[list[int]]:
        """Terms as ``[sign, base, exponent]``; the last term is a bare constant."""
        count = 2 if difficulty <= 2 else 3
        terms: list[list[int]] = []
        exponent = rng.randint(30, 120 + difficulty * 40)
        terms.append([1, base, exponent])
        for _ in range(count - 1):
            sign = 1 if rng.chance(0.6) else -1
            other = rng.choice([b for b in (base, base**2, 3, 5, 7, 9) if b > 1])
            power = rng.randint(10, max(11, exponent - 10))
            terms.append([sign, other, power])
        terms.append([1 if rng.chance(0.5) else -1, rng.randint(2, 200), 1])
        return terms

    def _positive(self, terms: list[list[int]]) -> bool:
        """Reject expressions whose subtractions overshoot: the exam never asks for
        the representation of a negative number."""
        return self._evaluate(terms) > 1

    def _format_expression(self, terms: list[list[int]]) -> str:
        parts: list[str] = []
        for i, (sign, value, power) in enumerate(terms):
            body = f"{value}^{power}" if power > 1 else f"{value}"
            if i == 0:
                parts.append(body if sign > 0 else f"−{body}")
            else:
                parts.append(("+ " if sign > 0 else "− ") + body)
        return " ".join(parts)

    def _evaluate(self, terms: list[list[int]]) -> int:
        return sum(sign * value**power for sign, value, power in terms)

    def _unknown_digit_problem(
        self, rng: Rng, base: int, difficulty: int
    ) -> tuple[str | None, int]:
        """A numeral with one unknown digit, divisible by k for exactly one value."""
        length = 3 if difficulty <= 2 else 4
        divisor = rng.choice([3, 4, 5, 6, 7, 8, 9, 11])
        digits = [DIGITS[rng.randint(0, base - 1)] for _ in range(length)]
        if digits[0] == "0":
            digits[0] = DIGITS[rng.randint(1, base - 1)]
        position = rng.randint(1, length - 1)
        digits[position] = "x"
        pattern = "".join(digits)
        hits = [d for d in range(base) if int(pattern.replace("x", DIGITS[d]), base) % divisor == 0]
        return (pattern, divisor) if len(hits) == 1 else (None, divisor)

    # -- solving ------------------------------------------------------------
    def solve_fast(self, meta: dict[str, Any]) -> str:
        match meta["question"]:
            case "count":
                text = to_base(self._evaluate(meta["terms"]), meta["base"])
                return str(text.count(DIGITS[meta["digit"]]))
            case "digit_sum":
                text = to_base(self._evaluate(meta["terms"]), meta["base"])
                return str(sum(DIGITS.index(ch) for ch in text))
            case "unknown_digit":
                hits = self._digit_candidates(meta)
                return str(hits[0]) if len(hits) == 1 else ""
            case "min_base":
                bases = self._base_candidates(meta)
                return str(bases[0]) if bases else ""
            case "mixed":
                total = int(meta["left"], meta["left_base"]) + int(
                    meta["right"], meta["right_base"]
                )
                text = to_base(total, meta["base"])
                return str(text.count(DIGITS[meta["digit"]]))
        raise ValueError(meta["question"])

    def solve_naive(self, meta: dict[str, Any]) -> str | None:
        """Convert by greedily subtracting powers instead of dividing repeatedly."""

        def convert(value: int, base: int) -> str:
            if value == 0:
                return "0"
            power = 1
            while power * base <= value:
                power *= base
            out: list[str] = []
            while power:
                digit = 0
                while value >= power:
                    value -= power
                    digit += 1
                out.append(DIGITS[digit])
                power //= base
            return "".join(out)

        def value_of(text: str, base: int) -> int:
            total = 0
            for ch in text:
                total = total * base + DIGITS.index(ch.upper())
            return total

        match meta["question"]:
            case "count":
                text = convert(self._evaluate(meta["terms"]), meta["base"])
                return str(text.count(DIGITS[meta["digit"]]))
            case "digit_sum":
                text = convert(self._evaluate(meta["terms"]), meta["base"])
                return str(sum(DIGITS.index(ch) for ch in text))
            case "unknown_digit":
                hits = [
                    d
                    for d in range(meta["base"])
                    if value_of(meta["pattern"].replace("x", DIGITS[d]), meta["base"])
                    % meta["divisor"]
                    == 0
                ]
                return str(hits[0]) if len(hits) == 1 else None
            case "min_base":
                value = self._evaluate(meta["terms"])
                for base in range(2, 37):
                    if convert(value, base).endswith("0" * meta["zeros"]):
                        return str(base)
                return None
            case "mixed":
                total = value_of(meta["left"], meta["left_base"]) + value_of(
                    meta["right"], meta["right_base"]
                )
                text = convert(total, meta["base"])
                return str(text.count(DIGITS[meta["digit"]]))
        return None

    def _digit_candidates(self, meta: dict[str, Any]) -> list[int]:
        return [
            d
            for d in range(meta["base"])
            if int(meta["pattern"].replace("x", DIGITS[d]), meta["base"]) % meta["divisor"] == 0
        ]

    def _base_candidates(self, meta: dict[str, Any]) -> list[int]:
        value = self._evaluate(meta["terms"])
        return [base for base in range(2, 37) if to_base(value, base).endswith("0" * meta["zeros"])]

    def enumerate_answers(self, meta: dict[str, Any]) -> list[str] | None:
        if meta["question"] == "unknown_digit":
            return [str(d) for d in self._digit_candidates(meta)]
        if meta["question"] == "min_base":
            bases = self._base_candidates(meta)
            return [str(bases[0])] if bases else []
        return None

    def validate_answer(self, answer: str, meta: dict[str, Any]) -> None:
        if not answer:
            raise ValueError("t14: no answer")

    # -- explanation --------------------------------------------------------
    def _solution(self, meta: dict[str, Any], answer: str) -> list[str]:
        helper = (
            "def to_base(n, b):\n"
            "    d = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ'; r = ''\n"
            "    while n: r = d[n % b] + r; n //= b\n"
            "    return r or '0'"
        )
        match meta["question"]:
            case "count" | "digit_sum":
                expr = " ".join(
                    ("+" if sign > 0 else "-") + f" {value}**{power}"
                    for sign, value, power in meta["terms"]
                ).lstrip("+ ")
                text = to_base(self._evaluate(meta["terms"]), meta["base"])
                what = (
                    f".count('{DIGITS[meta['digit']]}')"
                    if meta["question"] == "count"
                    else " — сумма цифр"
                )
                return [
                    "**Шаг 1.** Python считает большие числа точно, поэтому значение "
                    "выражения вычисляем как есть, не упрощая его вручную.",
                    f"**Шаг 2.** Переводим в систему с основанием {meta['base']}:\n\n"
                    f"```python\n{helper}\n\nprint(to_base({expr}, {meta['base']})"
                    f"{what if meta['question'] == 'count' else ''})\n```",
                    f"**Шаг 3.** Запись содержит {len(text)} цифр, искомая величина — "
                    f"**{answer}**.",
                ]
            case "unknown_digit":
                return [
                    f"**Шаг 1.** Неизвестная цифра x может принимать значения от 0 до "
                    f"{meta['base'] - 1}. Подставляем каждое и проверяем делимость.",
                    "**Шаг 2.** Важно: `int('1x2', 7)` с буквой x не работает — "
                    "нужно подставлять именно цифру:\n\n```python\n"
                    f"for x in range({meta['base']}):\n"
                    f"    n = int('{meta['pattern']}'.replace('x', str(x)), {meta['base']})\n"
                    f"    if n % {meta['divisor']} == 0: print(x, n)\n```",
                    f"**Шаг 3.** Подходит ровно одно значение: x = **{answer}**.",
                ]
            case "min_base":
                return [
                    "**Шаг 1.** Вычисляем значение выражения точно.",
                    f"**Шаг 2.** Перебираем основание b начиная с 2 и смотрим, "
                    f"когда запись заканчивается на {meta['zeros']} "
                    f"{'ноль' if meta['zeros'] == 1 else 'нуля'}.",
                    f"**Шаг 3.** Наименьшее такое основание — **{answer}**.",
                ]
            case "mixed":
                return [
                    f"**Шаг 1.** Переводим оба числа в десятичную систему: "
                    f"`int('{meta['left']}', {meta['left_base']})` и "
                    f"`int('{meta['right']}', {meta['right_base']})`.",
                    f"**Шаг 2.** Складываем и переводим сумму в систему с основанием "
                    f"{meta['base']}.",
                    f"**Шаг 3.** Считаем нужную величину: **{answer}**.",
                ]
        return []


register(Task14())
