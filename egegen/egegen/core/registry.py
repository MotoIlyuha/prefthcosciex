"""Generator registry: task type -> generator instance."""

from __future__ import annotations

from typing import TYPE_CHECKING

from egegen.core.errors import GeneratorNotFoundError

if TYPE_CHECKING:
    from egegen.core.generator import Generator

registry: dict[int, Generator] = {}


def register(generator: Generator) -> Generator:
    """Register a generator, used as a decorator on generator classes."""
    if generator.task_no in registry:
        raise ValueError(f"task type {generator.task_no} is already registered")
    registry[generator.task_no] = generator
    return generator


def get_generator(task_no: int) -> Generator:
    _ensure_loaded()
    try:
        return registry[task_no]
    except KeyError as exc:
        raise GeneratorNotFoundError(f"no generator for task type {task_no}") from exc


def list_generators() -> list[Generator]:
    _ensure_loaded()
    return [registry[k] for k in sorted(registry)]


def _ensure_loaded() -> None:
    if not registry:
        import egegen.generators  # noqa: F401  (import registers every generator)
