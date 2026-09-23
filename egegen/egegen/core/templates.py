"""Formulation templates.

Statement wording lives in ``egegen/config/templates/tNN.yaml`` so a methodologist
can add or reword a phrasing without touching Python. Each task type ships at least
five templates; the generator picks one deterministically from the seed.
"""

from __future__ import annotations

import string
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

import yaml

from egegen.core.errors import ConfigError
from egegen.core.rng import Rng

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "config" / "templates"


@dataclass(frozen=True, slots=True)
class Template:
    id: str
    subtype: str
    text: str


@dataclass(frozen=True, slots=True)
class SubtypeSpec:
    id: str
    title: str
    difficulty_range: tuple[int, int]
    target_seconds: int


@dataclass(frozen=True, slots=True)
class TaskTemplates:
    task_no: int
    title: str
    subtypes: dict[str, SubtypeSpec]
    templates: list[Template]

    def for_subtype(self, subtype: str) -> list[Template]:
        matching = [t for t in self.templates if t.subtype in (subtype, "*")]
        if not matching:
            raise ConfigError(f"t{self.task_no:02d}: no template for subtype {subtype!r}")
        return matching

    def pick(self, rng: Rng, subtype: str) -> Template:
        return rng.choice(sorted(self.for_subtype(subtype), key=lambda t: t.id))


class _SafeFormatter(string.Formatter):
    """Formatter that fails loudly on an unknown placeholder.

    A silently-empty placeholder would ship a broken statement to a student, so a
    missing key is a hard error surfaced during template tests.
    """

    def get_value(self, key: Any, args: Any, kwargs: Any) -> Any:
        if isinstance(key, str):
            if key not in kwargs:
                raise ConfigError(f"template placeholder {{{key}}} has no value")
            return kwargs[key]
        return super().get_value(key, args, kwargs)


_FORMATTER = _SafeFormatter()


def render(template: Template, **values: Any) -> str:
    return _FORMATTER.vformat(template.text, (), values).strip()


@cache
def load_templates(task_no: int) -> TaskTemplates:
    path = TEMPLATES_DIR / f"t{task_no:02d}.yaml"
    if not path.exists():
        raise ConfigError(f"missing template file {path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ConfigError(f"{path}: expected a mapping at the top level")

    subtypes: dict[str, SubtypeSpec] = {}
    for sid, spec in (raw.get("subtypes") or {}).items():
        lo, hi = spec.get("difficulty", [1, 5])
        subtypes[sid] = SubtypeSpec(
            id=sid,
            title=spec["title"],
            difficulty_range=(int(lo), int(hi)),
            target_seconds=int(spec.get("target_seconds", 120)),
        )
    if not subtypes:
        raise ConfigError(f"{path}: at least one subtype is required")

    templates = [
        Template(id=t["id"], subtype=t.get("subtype", "*"), text=t["text"])
        for t in (raw.get("templates") or [])
    ]
    if len(templates) < 5:
        raise ConfigError(
            f"{path}: at least 5 formulation templates required, got {len(templates)}"
        )
    for t in templates:
        if t.subtype != "*" and t.subtype not in subtypes:
            raise ConfigError(f"{path}: template {t.id} references unknown subtype {t.subtype!r}")

    return TaskTemplates(
        task_no=int(raw["task_no"]),
        title=str(raw["title"]),
        subtypes=subtypes,
        templates=templates,
    )
