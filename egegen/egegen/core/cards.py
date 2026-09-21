"""Method cards — the short "how to attack this" text shown after a wrong answer.

Cards live in ``egegen/config/cards/tNN.md`` as Markdown with ``### <subtype>``
sections, editable by a methodologist without a developer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from egegen.core.errors import ConfigError

CARDS_DIR = Path(__file__).resolve().parent.parent / "config" / "cards"
_SECTION = re.compile(r"^###\s+(?P<id>[\w.-]+)\s*$", re.MULTILINE)


@dataclass(frozen=True, slots=True)
class MethodCard:
    id: str
    task_no: int
    subtype: str
    body_md: str


@lru_cache(maxsize=None)
def load_cards(task_no: int) -> dict[str, MethodCard]:
    path = CARDS_DIR / f"t{task_no:02d}.md"
    if not path.exists():
        raise ConfigError(f"missing method card file {path}")
    text = path.read_text(encoding="utf-8")

    cards: dict[str, MethodCard] = {}
    matches = list(_SECTION.finditer(text))
    if not matches:
        raise ConfigError(f"{path}: no '### <subtype>' sections found")
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        subtype = m.group("id")
        body = text[m.end() : end].strip()
        if not body:
            raise ConfigError(f"{path}: card {subtype!r} is empty")
        card_id = f"t{task_no:02d}:{subtype}"
        cards[subtype] = MethodCard(card_id, task_no, subtype, body)
    return cards


def card_id_for(task_no: int, subtype: str) -> str:
    """Resolve the card for a subtype, falling back to the task-wide ``common`` card."""
    cards = load_cards(task_no)
    if subtype in cards:
        return cards[subtype].id
    if "common" in cards:
        return cards["common"].id
    raise ConfigError(f"t{task_no:02d}: no card for subtype {subtype!r} and no 'common' card")


def get_card(card_id: str) -> MethodCard:
    task_part, _, subtype = card_id.partition(":")
    task_no = int(task_part.removeprefix("t"))
    cards = load_cards(task_no)
    if subtype not in cards:
        raise ConfigError(f"unknown method card {card_id!r}")
    return cards[subtype]


def all_cards() -> list[MethodCard]:
    out: list[MethodCard] = []
    for tt in range(1, 28):
        out.extend(load_cards(tt).values())
    return out
