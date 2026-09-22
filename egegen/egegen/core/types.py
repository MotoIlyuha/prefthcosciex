"""Core data types shared by every generator.

Field names follow the design doc (section 7.2): ``task_no``, ``assets``,
``answer_kind``, ``checker``, ``solution_steps``, ``reference_code``, ``exam_like``.
The ``generate(seed, difficulty, subtype)`` argument order follows the build prompt.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Any, Literal

AnswerKind = Literal["int", "letters", "two_ints", "pairs_list", "string", "float"]
"""Canonical answer shapes. Each maps to a checker in :mod:`egegen.checkers`."""


class Uniqueness(str, Enum):
    """How a generator proves its instance has exactly one correct answer."""

    ENUMERATED = "enumerated"
    """The generator sweeps the full answer space; tests assert a single hit."""

    FUNCTIONAL = "functional"
    """The answer is a deterministic function of the stated input, computed by two
    independent solvers. Uniqueness follows from both agreeing on every seed."""


@dataclass(frozen=True, slots=True)
class Attachment:
    """A file shipped with the statement (schema, table, dataset)."""

    name: str
    mime: str
    kind: Literal["svg", "csv", "ods", "txt", "json", "gz"]
    content: bytes
    inline: bool = False
    """True when the client renders the content in place (SVG schemas)."""
    deferred: bool = False
    """True for assets the worker builds asynchronously (task 27's file B)."""

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.content).hexdigest()

    @property
    def size(self) -> int:
        return len(self.content)


@dataclass(slots=True)
class Instance:
    """One generated task: everything the client, the checker and the solvers need."""

    task_no: int
    subtype: str
    difficulty: int
    seed: int
    statement_md: str
    answer: str
    solution_steps: list[str]
    answer_kind: AnswerKind | str = ""
    """Left empty by ``build`` to inherit the generator's default; a subtype that
    answers in a different shape (task 4 returns a code word, not a count) sets it."""
    checker: str = ""
    method_card_id: str = ""
    target_seconds: int = 0
    hidden_seed: int = 0
    """Seed of a sibling instance used to re-check submitted code server-side."""
    reference_code: str | None = None
    """Python that produces ``answer`` when run against this instance's assets."""
    exam_like: bool = True
    version: str = "1.0.0"
    assets: list[Attachment] = field(default_factory=list)
    requires_code: bool = False
    checker_options: dict[str, Any] = field(default_factory=dict)
    uniqueness: Uniqueness | None = None
    """Left unset by ``build`` to inherit the generator's default; a subtype whose
    answer space can be swept while its siblings' cannot sets it per instance."""
    template_id: str = ""
    meta: dict[str, Any] = field(default_factory=dict)
    """Generator parameters. Feeds the solvers and analytics; never sent to a client."""

    @property
    def solution_md(self) -> str:
        """The full worked solution, numbers of this very instance substituted in."""
        return "\n\n".join(self.solution_steps)

    def public_dict(self) -> dict[str, Any]:
        """Client-facing projection: no answer, no meta, no hidden seed."""
        return {
            "task_no": self.task_no,
            "subtype": self.subtype,
            "difficulty": self.difficulty,
            "statement_md": self.statement_md,
            "answer_kind": self.answer_kind,
            "checker": self.checker,
            "checker_options": self.checker_options,
            "method_card_id": self.method_card_id,
            "target_seconds": self.target_seconds,
            "requires_code": self.requires_code,
            "exam_like": self.exam_like,
            "assets": [
                {
                    "name": a.name,
                    "mime": a.mime,
                    "kind": a.kind,
                    "size": a.size,
                    "sha256": a.sha256,
                    "inline": a.inline,
                    "deferred": a.deferred,
                    "content": a.content.decode("utf-8") if a.inline else None,
                }
                for a in self.assets
            ],
        }

    def answer_hash(self) -> str:
        """Stored instead of the answer itself where the answer must not be at rest."""
        return hashlib.sha256(f"{self.seed}|{self.answer}".encode()).hexdigest()


def derive_seed(user_id: int, day: date, task_no: int, attempt_no: int, slot: str = "") -> int:
    """seed = hash(user_id, date, task_no, attempt_no) — the only source of tasks.

    Blake2b keeps the mapping collision-free in practice and, unlike :func:`hash`,
    is stable across processes and Python versions.
    """
    payload = f"{user_id}|{day.isoformat()}|{task_no}|{attempt_no}|{slot}".encode()
    digest = hashlib.blake2b(payload, digest_size=8).digest()
    return int.from_bytes(digest, "big") & 0x7FFF_FFFF_FFFF_FFFF


def derive_hidden_seed(seed: int) -> int:
    """Seed of the hidden sibling variant used by the anti-cheat code re-check."""
    digest = hashlib.blake2b(f"hidden|{seed}".encode(), digest_size=8).digest()
    return int.from_bytes(digest, "big") & 0x7FFF_FFFF_FFFF_FFFF
