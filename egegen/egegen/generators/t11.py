"""Task 11 — memory for passwords and identifiers.

Two ceilings in a row are what this task is really about: ``i = ceil(log2 K)`` bits
per symbol, then ``ceil(L·i/8)`` bytes per record — rounded **per record**, not for
the database as a whole. The naive solver does both by counting upward in a loop, so
a missing ceiling in the fast formula cannot slip through.
"""

from __future__ import annotations

from typing import Any

from egegen.core.errors import GenerationFailedError
from egegen.core.generator import Generator
from egegen.core.registry import register
from egegen.core.rng import Rng
from egegen.core.templates import render
from egegen.core.types import Instance, Uniqueness
from egegen.solvers.numbers import bits_per_symbol, bytes_for_bits

ALPHABET_CHOICES = [
    (10, "десяти десятичных цифр"),
    (12, "двенадцати различных символов"),
    (26, "26 строчных латинских букв"),
    (30, "30 различных символов"),
    (32, "32 букв русского алфавита (без «ё»)"),
    (33, "33 букв русского алфавита"),
    (36, "26 латинских букв и 10 цифр"),
    (52, "52 латинских букв (строчных и прописных)"),
    (62, "62 символов: латинские буквы обоих регистров и цифры"),
]
BYTE_UNITS = {"байт": 1, "Кбайт": 1024, "Мбайт": 1024 * 1024}


class Task11(Generator):
    task_no = 11
    answer_kind = "int"
    checker = "exact"
    uniqueness = Uniqueness.ENUMERATED

    def build(self, rng: Rng, difficulty: int, subtype: str) -> Instance:
        for _ in range(80):
            candidate = self._attempt(rng, difficulty, subtype)
            if candidate is not None:
                return candidate
            rng = rng.fork("retry")
        raise GenerationFailedError(f"t11/{subtype}: no valid instance")

    def _attempt(self, rng: Rng, difficulty: int, subtype: str) -> Instance | None:
        alphabet, alphabet_ru = rng.choice(ALPHABET_CHOICES)
        length = rng.randint(6, 16)
        users = rng.choice([8, 16, 20, 30, 32, 50, 60, 64, 80, 100, 120, 128, 160, 200])
        extra = rng.choice([2, 4, 6, 8, 10, 12, 16, 20]) if difficulty >= 3 else 0

        meta: dict[str, Any] = {
            "subtype": subtype,
            "alphabet": alphabet,
            "length": length,
            "users": users,
            "extra": extra,
        }
        fields: dict[str, Any] = {
            "alphabet": alphabet,
            "alphabet_ru": alphabet_ru,
            "length": length,
            "users": users,
            "extra": extra,
        }

        match subtype:
            case "11.1_volume":
                meta["extra"] = 0
                fields["extra"] = 0
                unit = self._unit_for(meta, rng, difficulty)
                if unit is None:
                    return None
                meta["question"], meta["unit"] = "total", unit
                fields["unit"] = unit
            case "11.3_extra_fields":
                if extra == 0:
                    return None
                unit = self._unit_for(meta, rng, difficulty)
                if unit is None:
                    return None
                meta["question"], meta["unit"] = "total", unit
                fields["unit"] = unit
            case "11.2_find_param":
                meta["question"] = "find_length"
                total_bytes = self._per_record(meta) * users
                if total_bytes % BYTE_UNITS["байт"] or total_bytes < 16:
                    return None
                meta["total_bytes"] = total_bytes
                fields["total_bytes"] = total_bytes
                lengths = self._lengths_matching(meta, total_bytes)
                if lengths != [length]:
                    return None  # the reverse question must have a single answer
            case "11.4_max_symbols":
                meta["question"] = "max_length"
                budget = self._per_record(meta) * users
                meta["budget_bytes"] = budget
                fields["budget_bytes"] = budget
            case "11.5_two_alphabets":
                second_alphabet, second_ru = rng.choice(ALPHABET_CHOICES)
                second_length = rng.randint(3, 8)
                meta["question"] = "total_two"
                meta["alphabet2"] = second_alphabet
                meta["length2"] = second_length
                unit = self._unit_for(meta, rng, difficulty)
                if unit is None:
                    return None
                meta["unit"] = unit
                fields.update(
                    {
                        "alphabet2": second_alphabet,
                        "alphabet2_ru": second_ru,
                        "length2": second_length,
                        "unit": unit,
                    }
                )
            case _:
                return None

        answer = self.solve_fast(meta)
        if not 1 <= int(answer) <= 10**9:
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

    def _unit_for(self, meta: dict[str, Any], rng: Rng, difficulty: int) -> str | None:
        """Pick a unit in which the total comes out whole."""
        total = self._per_record(meta) * meta["users"]
        wanted = ["байт"] if difficulty <= 2 else ["Кбайт", "байт"]
        for unit in wanted:
            if total % BYTE_UNITS[unit] == 0 and total // BYTE_UNITS[unit] >= 1:
                return unit
        return None

    def _per_record(self, meta: dict[str, Any]) -> int:
        bits = meta["length"] * bits_per_symbol(meta["alphabet"])
        if meta["subtype"] == "11.5_two_alphabets" and "alphabet2" in meta:
            # Each fragment is encoded with its own symbol width, then the whole
            # identifier is rounded up to a whole number of bytes once.
            bits += meta["length2"] * bits_per_symbol(meta["alphabet2"])
        return bytes_for_bits(bits) + int(meta["extra"])

    def _lengths_matching(self, meta: dict[str, Any], total_bytes: int) -> list[int]:
        out: list[int] = []
        for candidate in range(1, 64):
            probe = {**meta, "length": candidate}
            if self._per_record(probe) * meta["users"] == total_bytes:
                out.append(candidate)
        return out

    # -- solving ------------------------------------------------------------
    def solve_fast(self, meta: dict[str, Any]) -> str:
        match meta["question"]:
            case "total" | "total_two":
                total = self._per_record(meta) * meta["users"]
                return str(total // BYTE_UNITS[meta["unit"]])
            case "find_length":
                matches = self._lengths_matching(meta, meta["total_bytes"])
                return str(matches[0]) if len(matches) == 1 else ""
            case "max_length":
                best = 0
                for candidate in range(1, 256):
                    probe = {**meta, "length": candidate}
                    if self._per_record(probe) * meta["users"] <= meta["budget_bytes"]:
                        best = candidate
                return str(best)
        raise ValueError(meta["question"])

    def solve_naive(self, meta: dict[str, Any]) -> str | None:
        """Count the ceilings upward instead of computing them."""

        def width(alphabet: int) -> int:
            bits, capacity = 0, 1
            while capacity < alphabet:
                capacity *= 2
                bits += 1
            return bits

        def whole_bytes(bits: int) -> int:
            size = 0
            while size * 8 < bits:
                size += 1
            return size

        def per_record(length: int) -> int:
            bits = length * width(meta["alphabet"])
            if meta["question"] == "total_two":
                bits += meta["length2"] * width(meta["alphabet2"])
            return whole_bytes(bits) + int(meta["extra"])

        def to_unit(total: int, unit: str) -> int | None:
            step = {"байт": 1, "Кбайт": 1024, "Мбайт": 1024 * 1024}[unit]
            return total // step if total % step == 0 else None

        match meta["question"]:
            case "total" | "total_two":
                value = to_unit(per_record(meta["length"]) * meta["users"], meta["unit"])
                return None if value is None else str(value)
            case "find_length":
                hits = [
                    n for n in range(1, 64) if per_record(n) * meta["users"] == meta["total_bytes"]
                ]
                return str(hits[0]) if len(hits) == 1 else None
            case "max_length":
                best = 0
                for n in range(1, 256):
                    if per_record(n) * meta["users"] <= meta["budget_bytes"]:
                        best = n
                return str(best)
        return None

    def enumerate_answers(self, meta: dict[str, Any]) -> list[str] | None:
        if meta["question"] == "find_length":
            return [str(n) for n in self._lengths_matching(meta, meta["total_bytes"])]
        answer = self.solve_fast(meta)
        return [answer] if answer else []

    def validate_answer(self, answer: str, meta: dict[str, Any]) -> None:
        if not answer or int(answer) < 1:
            raise ValueError("t11: answer must be a positive integer")

    # -- explanation --------------------------------------------------------
    def _solution(self, meta: dict[str, Any], answer: str) -> list[str]:
        i = bits_per_symbol(meta["alphabet"])
        bits = meta["length"] * i
        record = self._per_record(meta)
        steps = [
            f"**Шаг 1.** На один символ нужно i = ⌈log₂ {meta['alphabet']}⌉ = **{i}** бит "
            "(минимальное целое число бит).",
        ]
        if meta["question"] == "total_two":
            i2 = bits_per_symbol(meta["alphabet2"])
            bits = meta["length"] * i + meta["length2"] * i2
            steps.append(
                f"**Шаг 2.** Вторая часть идентификатора кодируется отдельно: "
                f"⌈log₂ {meta['alphabet2']}⌉ = {i2} бит на символ. "
                f"Всего на идентификатор {meta['length']} × {i} + {meta['length2']} × "
                f"{i2} = {bits} бит."
            )
        else:
            steps.append(f"**Шаг 2.** На одну запись {meta['length']} × {i} = {bits} бит.")
        steps.append(
            f"**Шаг 3.** Округляем **вверх до целого числа байт для каждой записи "
            f"отдельно**: ⌈{bits} / 8⌉ = {bytes_for_bits(bits)} байт"
            + (
                f", плюс {meta['extra']} байт дополнительных сведений → {record} байт."
                if meta["extra"]
                else "."
            )
        )
        match meta["question"]:
            case "total" | "total_two":
                total = record * meta["users"]
                steps.append(
                    f"**Шаг 4.** На {meta['users']} записей: {record} × "
                    f"{meta['users']} = {total} байт = **{answer}** {meta['unit']}."
                )
            case "find_length":
                steps.append(
                    f"**Шаг 4.** Обратная задача: перебираем длину и ищем ту, при "
                    f"которой объём равен {meta['total_bytes']} байт. Подходит ровно "
                    f"одна: **{answer}**."
                )
            case "max_length":
                steps.append(
                    f"**Шаг 4.** Перебираем длину, пока объём не превысит "
                    f"{meta['budget_bytes']} байт. Максимум — **{answer}** символов."
                )
        return steps


register(Task11())
