"""Tasks 10, 13, 23 and 27 must follow ``fipi_2027.yaml``, not hard-coded formats.

The November demo version may change the answer transform of 10 or the input
structure of 23; these tests are what guarantee that switching a knob is enough.
"""

from __future__ import annotations

import pytest

from egegen.core.fipi import FipiConfig, load_fipi_config, reload_fipi_config, set_fipi_config
from egegen.core.registry import registry


@pytest.fixture(autouse=True)
def _restore_config() -> object:
    yield
    reload_fipi_config()


def _with(section: str, **changes: object) -> FipiConfig:
    base = load_fipi_config()
    sub = getattr(base, section).model_copy(update=changes)
    return base.model_copy(update={section: sub})


def test_config_loads_and_validates() -> None:
    cfg = load_fipi_config()
    assert cfg.t10.answer_transform == "octet_sum", "2027 draft answers with the octet sum"
    assert cfg.t27.answer_layout == "one_line_pair", "2027 draft puts both numbers on one line"
    assert cfg.banner_ru, "the app shows a banner until the demo version is approved"


def test_rejects_unknown_keys() -> None:
    with pytest.raises(Exception):
        FipiConfig.model_validate({"version": "x", "source_note": "y", "banner_ru": "z", "oops": 1})


@pytest.mark.skipif(10 not in registry, reason="t10 not implemented")
@pytest.mark.parametrize("transform", ["octet_sum", "address_no_dots", "number"])
def test_task10_answer_transform_switches_without_code_change(transform: str) -> None:
    set_fipi_config(_with("t10", answer_transform=transform))
    instance = registry[10].generate(4242, 3, "10.1_same_network")
    assert instance.meta["answer_transform"] == transform
    assert registry[10].solve_fast(instance.meta) == instance.answer
    assert registry[10].solve_naive(instance.meta) == instance.answer


@pytest.mark.skipif(10 not in registry, reason="t10 not implemented")
def test_task10_transforms_give_different_answers() -> None:
    answers = set()
    for transform in ("octet_sum", "address_no_dots", "number"):
        set_fipi_config(_with("t10", answer_transform=transform))
        answers.add(registry[10].generate(4242, 3, "10.1_same_network").answer)
    assert len(answers) == 3, "the transform must actually change the answer"


@pytest.mark.skipif(13 not in registry, reason="t13 not implemented")
@pytest.mark.parametrize("commands", [["add1", "mul2"], ["add1", "add2", "mul2"], ["add2", "mul3"]])
def test_task13_command_set_comes_from_config(commands: list[str]) -> None:
    set_fipi_config(_with("t13", commands=commands))
    instance = registry[13].generate(777, 3)
    assert instance.meta["commands"] == commands
    assert registry[13].solve_naive(instance.meta) == instance.answer


@pytest.mark.skipif(23 not in registry, reason="t23 not implemented")
@pytest.mark.parametrize("fmt", ["matrix_ods", "edges_txt", "figure"])
def test_task23_input_format_switches_without_code_change(fmt: str) -> None:
    set_fipi_config(_with("t23", graph_input_format=fmt))
    instance = registry[23].generate(909, 3, "23.1_shortest_path")
    assert instance.meta["graph_input_format"] == fmt
    assert registry[23].solve_fast(instance.meta) == instance.answer
    kinds = {a.kind for a in instance.assets}
    expected = {"matrix_ods": "ods", "edges_txt": "txt", "figure": "svg"}[fmt]
    assert expected in kinds, f"{fmt} should ship a {expected} asset, got {kinds}"


@pytest.mark.skipif(27 not in registry, reason="t27 not implemented")
@pytest.mark.parametrize("layout", ["one_line_pair", "two_lines"])
def test_task27_answer_layout_switches_without_code_change(layout: str) -> None:
    set_fipi_config(_with("t27", answer_layout=layout))
    instance = registry[27].generate(31337, 3)
    assert instance.meta["answer_layout"] == layout
    if layout == "one_line_pair":
        assert "\n" not in instance.answer
    else:
        assert "\n" in instance.answer
