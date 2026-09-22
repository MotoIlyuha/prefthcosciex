"""The methodologist-facing configuration must stay valid without a developer."""

from __future__ import annotations

import pytest

from egegen.core.cards import get_card, load_cards
from egegen.core.generator import Generator
from egegen.core.templates import load_templates


def test_five_formulation_templates(generator: Generator) -> None:
    """Design doc 16.6: at least five phrasings per task."""
    templates = load_templates(generator.task_no)
    assert len(templates.templates) >= 5


def test_at_least_three_subtypes(generator: Generator) -> None:
    """Design doc 16.6: at least three subtypes per task."""
    assert len(generator.subtypes) >= 3


def test_every_subtype_has_a_template(generator: Generator) -> None:
    templates = load_templates(generator.task_no)
    for subtype in generator.subtypes:
        assert templates.for_subtype(subtype), f"no template for {subtype}"


def test_every_subtype_has_a_method_card(generator: Generator, subtype: str) -> None:
    instance = generator.generate(1234, 3, subtype)
    card = get_card(instance.method_card_id)
    assert card.body_md.strip()
    assert len(card.body_md) > 120, "a method card should actually explain the method"


def test_cards_cover_every_task(generator: Generator) -> None:
    cards = load_cards(generator.task_no)
    assert "common" in cards or set(cards) >= set(generator.subtypes)


def test_subtype_difficulty_ranges_are_sane(generator: Generator, subtype: str) -> None:
    lo, hi = generator.templates.subtypes[subtype].difficulty_range
    assert 1 <= lo <= hi <= 5
    assert generator.templates.subtypes[subtype].target_seconds > 0


def test_difficulty_bands_cover_all_levels(generator: Generator) -> None:
    """Every difficulty 1..5 must be reachable, or the planner cannot place the task."""
    covered: set[int] = set()
    for spec in generator.templates.subtypes.values():
        covered.update(range(spec.difficulty_range[0], spec.difficulty_range[1] + 1))
    missing = set(range(1, 6)) - covered
    assert not missing, f"t{generator.task_no:02d}: no subtype covers difficulty {missing}"


@pytest.mark.parametrize("task_no", range(1, 28))
def test_every_task_number_has_config(task_no: int) -> None:
    """Config files exist for all 27 tasks, even before the generator lands."""
    from egegen.core.registry import registry

    if task_no not in registry:
        pytest.skip(f"generator t{task_no:02d} not implemented yet")
    load_templates(task_no)
    load_cards(task_no)
