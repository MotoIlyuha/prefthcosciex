"""Shared fixtures for the generator test suite."""

from __future__ import annotations

import pytest

from egegen.core.generator import Generator
from egegen.core.registry import list_generators


def pytest_generate_tests(metafunc: pytest.Metafunc) -> None:
    """Parametrise over every registered generator, and over subtypes where asked."""
    if "generator" in metafunc.fixturenames and "subtype" in metafunc.fixturenames:
        cases = [
            pytest.param(gen, sid, id=f"t{gen.task_no:02d}-{sid}")
            for gen in list_generators()
            for sid in gen.subtypes
        ]
        metafunc.parametrize(("generator", "subtype"), cases)
    elif "generator" in metafunc.fixturenames:
        metafunc.parametrize(
            "generator",
            [pytest.param(g, id=f"t{g.task_no:02d}") for g in list_generators()],
        )


@pytest.fixture(scope="session")
def all_generators() -> list[Generator]:
    return list_generators()
