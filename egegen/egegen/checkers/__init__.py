"""Answer checkers.

Each :class:`~egegen.core.types.AnswerKind` maps to a checker that normalises a
student's raw input and compares it to the canonical answer. Normalisation is
deliberately forgiving about whitespace and separators (a student typing "12, 30"
means the same as "12 30") and deliberately strict about everything else.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from egegen.core.types import AnswerKind

_SEPARATORS = re.compile(r"[\s,;]+")


@dataclass(frozen=True, slots=True)
class CheckResult:
    correct: bool
    normalized: str
    reason: str = ""
    """Empty when correct; otherwise a Russian hint about the *format*, never the answer."""


def check_int(raw: str, expected: str, options: dict[str, Any] | None = None) -> CheckResult:
    text = raw.strip().replace(" ", "").replace(" ", "")
    if not re.fullmatch(r"[+-]?\d+", text):
        return CheckResult(False, text, "Ожидается целое число без лишних символов.")
    value = str(int(text))
    return CheckResult(value == str(int(expected)), value)


def check_float(raw: str, expected: str, options: dict[str, Any] | None = None) -> CheckResult:
    text = raw.strip().replace(" ", "").replace(" ", "").replace(",", ".")
    if not re.fullmatch(r"[+-]?\d+(\.\d+)?", text):
        return CheckResult(False, text, "Ожидается число, допускается десятичная дробь.")
    tolerance = float((options or {}).get("tolerance", 1e-6))
    ok = abs(float(text) - float(expected)) <= tolerance
    return CheckResult(ok, text)


def check_letters(raw: str, expected: str, options: dict[str, Any] | None = None) -> CheckResult:
    """Letter sequences (task 1/2/…): case-insensitive, separators ignored."""
    opts = options or {}
    text = _SEPARATORS.sub("", raw.strip()).upper()
    exp = _SEPARATORS.sub("", expected.strip()).upper()
    if not text:
        return CheckResult(False, text, "Введите последовательность букв.")
    alphabet = str(opts.get("alphabet", "")).upper()
    if alphabet and set(text) - set(alphabet):
        return CheckResult(False, text, f"Допустимы только буквы: {alphabet}.")
    if opts.get("length") and len(text) != int(opts["length"]):
        return CheckResult(False, text, f"Ожидается ровно {opts['length']} букв.")
    if opts.get("unordered"):
        return CheckResult(sorted(text) == sorted(exp), text)
    return CheckResult(text == exp, text)


def check_two_ints(raw: str, expected: str, options: dict[str, Any] | None = None) -> CheckResult:
    """Two integers (tasks 20, 26, 27). Order matters unless ``unordered`` is set."""
    opts = options or {}
    parts = [p for p in _SEPARATORS.split(raw.strip()) if p]
    if len(parts) != 2 or not all(re.fullmatch(r"[+-]?\d+", p) for p in parts):
        return CheckResult(False, " ".join(parts), "Ожидаются два целых числа через пробел.")
    got = [int(p) for p in parts]
    exp = [int(p) for p in _SEPARATORS.split(expected.strip()) if p]
    ok = sorted(got) == sorted(exp) if opts.get("unordered") else got == exp
    return CheckResult(ok, " ".join(str(v) for v in got))


def check_pairs_list(raw: str, expected: str, options: dict[str, Any] | None = None) -> CheckResult:
    """A list of pairs like ``12 30, 15 22``. Pair order is free, order inside a pair is not."""

    def parse(text: str) -> list[tuple[int, int]] | None:
        chunks = [c.strip() for c in text.replace(";", ",").split(",") if c.strip()]
        pairs: list[tuple[int, int]] = []
        for chunk in chunks:
            nums = [p for p in _SEPARATORS.split(chunk) if p]
            if len(nums) != 2 or not all(re.fullmatch(r"[+-]?\d+", p) for p in nums):
                return None
            pairs.append((int(nums[0]), int(nums[1])))
        return pairs

    got = parse(raw)
    if got is None or not got:
        return CheckResult(False, raw.strip(), "Ожидается список пар: «12 30, 15 22».")
    exp = parse(expected) or []
    normalized = ", ".join(f"{a} {b}" for a, b in got)
    return CheckResult(sorted(got) == sorted(exp), normalized)


def check_string(raw: str, expected: str, options: dict[str, Any] | None = None) -> CheckResult:
    opts = options or {}
    text = " ".join(raw.split())
    exp = " ".join(expected.split())
    if opts.get("case_insensitive", True):
        return CheckResult(text.lower() == exp.lower(), text)
    return CheckResult(text == exp, text)


Checker = Callable[[str, str, "dict[str, Any] | None"], CheckResult]

CHECKERS: dict[AnswerKind, Checker] = {
    "int": check_int,
    "float": check_float,
    "letters": check_letters,
    "two_ints": check_two_ints,
    "pairs_list": check_pairs_list,
    "string": check_string,
}


def check(
    answer_kind: AnswerKind,
    raw: str,
    expected: str,
    options: dict[str, Any] | None = None,
) -> CheckResult:
    """Dispatch to the checker for ``answer_kind``."""
    try:
        checker = CHECKERS[answer_kind]
    except KeyError as exc:
        raise ValueError(f"unknown answer kind {answer_kind!r}") from exc
    return checker(raw, expected, options)


__all__ = ["CHECKERS", "CheckResult", "check"]
