"""Answer checkers: forgiving about formatting, strict about correctness."""

from __future__ import annotations

import pytest

from egegen.checkers import check


@pytest.mark.parametrize(
    ("raw", "expected", "correct"),
    [("42", "42", True), (" 42 ", "42", True), ("042", "42", True), ("43", "42", False)],
)
def test_int(raw: str, expected: str, correct: bool) -> None:
    assert check("int", raw, expected).correct is correct


def test_int_rejects_junk() -> None:
    result = check("int", "42 км", "42")
    assert not result.correct
    assert "целое число" in result.reason


@pytest.mark.parametrize(
    ("raw", "correct"),
    [("12 30", True), ("12,30", True), ("12  30", True), ("30 12", False), ("12", False)],
)
def test_two_ints(raw: str, correct: bool) -> None:
    assert check("two_ints", raw, "12 30").correct is correct


def test_two_ints_unordered() -> None:
    assert check("two_ints", "30 12", "12 30", {"unordered": True}).correct


@pytest.mark.parametrize(
    ("raw", "correct"), [("xzwy", True), ("XZWY", True), ("x z w y", True), ("xzyw", False)]
)
def test_letters(raw: str, correct: bool) -> None:
    assert check("letters", raw, "xzwy").correct is correct


def test_letters_alphabet_is_enforced() -> None:
    result = check("letters", "0102", "0101", {"alphabet": "01"})
    assert not result.correct
    result = check("letters", "0a01", "0101", {"alphabet": "01"})
    assert "Допустимы только буквы" in result.reason


def test_pairs_list_order_free_between_pairs() -> None:
    assert check("pairs_list", "15 22, 12 30", "12 30, 15 22").correct
    assert not check("pairs_list", "30 12, 15 22", "12 30, 15 22").correct


def test_pairs_list_reports_format() -> None:
    result = check("pairs_list", "12", "12 30")
    assert not result.correct
    assert "список пар" in result.reason


def test_unknown_kind_raises() -> None:
    with pytest.raises(ValueError):
        check("nope", "1", "1")  # type: ignore[arg-type]
