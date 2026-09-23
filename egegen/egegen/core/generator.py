"""The contract every task generator implements (design doc 7.1–7.2)."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any

from egegen.core.cards import card_id_for
from egegen.core.errors import UnknownSubtypeError
from egegen.core.rng import Rng
from egegen.core.templates import TaskTemplates, load_templates
from egegen.core.types import AnswerKind, Instance, Uniqueness, derive_hidden_seed


class Generator(ABC):
    """Base class for the 27 task generators.

    A subclass implements :meth:`build`, :meth:`solve_fast` and :meth:`solve_naive`.
    The two solvers must use genuinely different algorithms — that disagreement is
    what the property tests exist to catch (design doc 7.1.3).
    """

    task_no: int
    answer_kind: AnswerKind
    checker: str = "exact"
    version: str = "1.0.0"
    requires_code: bool = False
    uniqueness: Uniqueness = Uniqueness.FUNCTIONAL
    #: Wall-clock budget for one instance (doc 7.2(д): 200 ms; 27 runs in the worker).
    generation_budget_ms: int = 200
    #: Seeds the property sweep uses. Generators that build a 10^6-number file are
    #: swept less densely so the suite stays runnable; their budget is the guard.
    sweep_seeds: int = 25

    # -- configuration ------------------------------------------------------
    @property
    def templates(self) -> TaskTemplates:
        return load_templates(self.task_no)

    @property
    def subtypes(self) -> tuple[str, ...]:
        return tuple(self.templates.subtypes)

    @property
    def title(self) -> str:
        return self.templates.title

    # -- generation ---------------------------------------------------------
    def generate(self, seed: int, difficulty: int = 3, subtype: str | None = None) -> Instance:
        """Build one instance. Pure function of (seed, difficulty, subtype)."""
        if not 1 <= difficulty <= 5:
            raise ValueError(f"difficulty must be 1..5, got {difficulty}")
        rng = Rng(seed)
        if subtype is None:
            subtype = self._pick_subtype(rng, difficulty)
        elif subtype not in self.subtypes:
            raise UnknownSubtypeError(f"t{self.task_no:02d} has no subtype {subtype!r}")

        instance = self.build(rng.fork(f"build:{subtype}:{difficulty}"), difficulty, subtype)
        instance.seed = seed
        instance.hidden_seed = derive_hidden_seed(seed)
        instance.task_no = self.task_no
        instance.subtype = subtype
        instance.difficulty = difficulty
        instance.requires_code = self.requires_code
        if instance.uniqueness is None:
            instance.uniqueness = self.uniqueness
        if not instance.answer_kind:
            instance.answer_kind = self.answer_kind
        instance.version = self.version
        if not instance.checker:
            instance.checker = self.checker
        if not instance.method_card_id:
            instance.method_card_id = card_id_for(self.task_no, subtype)
        if not instance.target_seconds:
            instance.target_seconds = self.target_seconds_for(subtype, difficulty)
        return instance

    def generate_hidden(self, instance: Instance) -> Instance:
        """The sibling variant used to re-check submitted code server-side (doc 7.5.2).

        Same subtype and difficulty, different data — so an answer hard-coded from the
        visible variant fails here.
        """
        return self.generate(instance.hidden_seed, instance.difficulty, instance.subtype)

    def _pick_subtype(self, rng: Rng, difficulty: int) -> str:
        """Choose among the subtypes whose declared difficulty band covers ``difficulty``."""
        specs = self.templates.subtypes
        eligible = sorted(
            sid
            for sid, spec in specs.items()
            if spec.difficulty_range[0] <= difficulty <= spec.difficulty_range[1]
        )
        return rng.choice(eligible or sorted(specs))

    @abstractmethod
    def build(self, rng: Rng, difficulty: int, subtype: str) -> Instance:
        """Produce the instance body. The framework fills in the identity fields."""

    # -- solving ------------------------------------------------------------
    @abstractmethod
    def solve_fast(self, meta: dict[str, Any]) -> str:
        """The intended, efficient solution. Its output becomes ``Instance.answer``."""

    @abstractmethod
    def solve_naive(self, meta: dict[str, Any]) -> str | None:
        """An independent brute-force solution, or ``None`` when it would be too costly.

        Returning ``None`` is only allowed when the instance's parameters put the naive
        sweep out of reach; property tests then fall back to the enumeration check.
        """

    def enumerate_answers(self, meta: dict[str, Any]) -> list[str] | None:
        """Every answer satisfying the statement, when the space can be swept.

        ``None`` means the task is functional (the answer is a computed value, not a
        search), and uniqueness rests on the two solvers agreeing.
        """
        return None

    def validate_answer(self, answer: str, meta: dict[str, Any]) -> None:
        """Raise if the produced answer falls outside the range the task promises.

        The default accepts anything: most generators bound their answer by
        construction, and only the ones that cannot need to override this.
        """
        return

    # -- helpers ------------------------------------------------------------
    def target_seconds_for(self, subtype: str, difficulty: int) -> int:
        base = self.templates.subtypes[subtype].target_seconds
        # Difficulty 3 is the reference; each step moves the budget by 15%.
        return max(30, round(base * (1 + 0.15 * (difficulty - 3))))

    def timed_generate(
        self, seed: int, difficulty: int = 3, subtype: str | None = None
    ) -> tuple[Instance, float]:
        started = time.perf_counter()
        inst = self.generate(seed, difficulty, subtype)
        return inst, (time.perf_counter() - started) * 1000.0
