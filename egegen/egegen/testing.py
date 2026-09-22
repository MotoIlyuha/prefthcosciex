"""Property checks every generator must pass (design doc 7.2).

The same checks back the pytest suite, the ``egegen check`` CLI and the stage
smoke test, so "it passed in CI" and "it passed on the server" mean the same thing.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from egegen.checkers import check
from egegen.core.generator import Generator
from egegen.core.types import Instance, Uniqueness

PLACEHOLDER = re.compile(r"\{[a-zA-Z_][a-zA-Z0-9_]*\}")
"""Leftover ``{name}`` in a statement means a template was rendered with a gap."""

_STRAY_SCRIPT = re.compile(r"[\u3000-\u9fff\u0600-\u06ff\u0e00-\u0e7f]")
"""CJK, Arabic or Thai in a Russian statement means a character slipped in."""

_CODE_BLOCK = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE = re.compile(r"`[^`\n]*`")


def _prose_only(text: str) -> str:
    """Strip code so a Python f-string in a worked solution is not mistaken for a gap."""
    return _INLINE_CODE.sub("", _CODE_BLOCK.sub("", text))


@dataclass(slots=True)
class CheckReport:
    generator: str
    subtype: str
    seed: int
    difficulty: int
    failures: list[str] = field(default_factory=list)
    gen_ms: float = 0.0

    @property
    def ok(self) -> bool:
        return not self.failures

    def __str__(self) -> str:
        head = f"t{self.generator}/{self.subtype} seed={self.seed} d={self.difficulty}"
        if self.ok:
            return f"{head}: ok ({self.gen_ms:.0f} ms)"
        return f"{head}: " + "; ".join(self.failures)


def check_instance(
    gen: Generator, seed: int, difficulty: int, subtype: str, *, budget_ms: float | None = None
) -> CheckReport:
    """Run every invariant against one generated instance."""
    report = CheckReport(f"{gen.task_no:02d}", subtype, seed, difficulty)
    budget = budget_ms if budget_ms is not None else gen.generation_budget_ms

    try:
        instance, gen_ms = gen.timed_generate(seed, difficulty, subtype)
    except Exception as exc:  # noqa: BLE001 - any failure is a test failure
        report.failures.append(f"generate raised {type(exc).__name__}: {exc}")
        return report
    report.gen_ms = gen_ms

    if gen_ms > budget:
        report.failures.append(f"generation took {gen_ms:.0f} ms, budget {budget} ms")

    _check_determinism(gen, instance, seed, difficulty, subtype, report)
    _check_statement(instance, report)
    _check_answer_format(instance, report)
    _check_solvers(gen, instance, report)
    _check_uniqueness(gen, instance, report)
    _check_metadata(gen, instance, report)
    return report


def _check_determinism(
    gen: Generator,
    instance: Instance,
    seed: int,
    difficulty: int,
    subtype: str,
    report: CheckReport,
) -> None:
    twin = gen.generate(seed, difficulty, subtype)
    if twin.answer != instance.answer:
        report.failures.append(f"non-deterministic answer: {instance.answer} vs {twin.answer}")
    if twin.statement_md != instance.statement_md:
        report.failures.append("non-deterministic statement")
    if [a.sha256 for a in twin.assets] != [a.sha256 for a in instance.assets]:
        report.failures.append("non-deterministic assets")


def _check_statement(instance: Instance, report: CheckReport) -> None:
    if not instance.statement_md.strip():
        report.failures.append("empty statement")
    leftover = PLACEHOLDER.findall(_prose_only(instance.statement_md))
    if leftover:
        report.failures.append(f"unfilled placeholders in statement: {leftover}")
    if not instance.solution_steps:
        report.failures.append("no solution steps")
    for step in instance.solution_steps:
        gaps = PLACEHOLDER.findall(_prose_only(step))
        if gaps:
            report.failures.append(f"unfilled placeholder in solution: {gaps}")
            break
    if instance.requires_code and instance.reference_code is None:
        report.failures.append("code task without reference_code")
    for label, text in (
        ("statement", instance.statement_md),
        ("solution", instance.solution_md),
    ):
        stray = _STRAY_SCRIPT.findall(text)
        if stray:
            report.failures.append(f"stray non-Russian characters in {label}: {stray[:5]}")


def _check_answer_format(instance: Instance, report: CheckReport) -> None:
    result = check(
        instance.answer_kind, instance.answer, instance.answer, instance.checker_options
    )
    if not result.correct:
        report.failures.append(
            f"answer {instance.answer!r} does not validate as {instance.answer_kind}: "
            f"{result.reason}"
        )


def _check_solvers(gen: Generator, instance: Instance, report: CheckReport) -> None:
    try:
        fast = gen.solve_fast(instance.meta)
    except Exception as exc:  # noqa: BLE001
        report.failures.append(f"solve_fast raised {type(exc).__name__}: {exc}")
        return
    if fast != instance.answer:
        report.failures.append(f"solve_fast {fast!r} != instance answer {instance.answer!r}")
    try:
        naive = gen.solve_naive(instance.meta)
    except Exception as exc:  # noqa: BLE001
        report.failures.append(f"solve_naive raised {type(exc).__name__}: {exc}")
        return
    if naive is not None and naive != instance.answer:
        report.failures.append(f"solve_naive {naive!r} != instance answer {instance.answer!r}")
    if naive is None and gen.enumerate_answers(instance.meta) is None:
        report.failures.append(
            "solve_naive declined and no enumerate_answers: nothing cross-checks the answer"
        )
    try:
        gen.validate_answer(instance.answer, instance.meta)
    except Exception as exc:  # noqa: BLE001
        report.failures.append(f"validate_answer rejected {instance.answer!r}: {exc}")


def _check_uniqueness(gen: Generator, instance: Instance, report: CheckReport) -> None:
    answers = gen.enumerate_answers(instance.meta)
    if answers is None:
        if gen.uniqueness is Uniqueness.ENUMERATED:
            report.failures.append("declared ENUMERATED but enumerate_answers returned None")
        return
    if len(answers) != 1:
        report.failures.append(f"answer is not unique: {answers[:6]}")
    elif answers[0] != instance.answer:
        report.failures.append(f"enumerated answer {answers[0]!r} != {instance.answer!r}")


def _check_metadata(gen: Generator, instance: Instance, report: CheckReport) -> None:
    if not instance.answer_kind:
        report.failures.append("answer_kind was never set")
    if not instance.checker:
        report.failures.append("checker was never set")
    if instance.target_seconds <= 0:
        report.failures.append("target_seconds must be positive")
    if not instance.method_card_id:
        report.failures.append("missing method_card_id")
    if instance.hidden_seed == instance.seed:
        report.failures.append("hidden_seed must differ from seed")
    if not _json_safe(instance.meta):
        report.failures.append("meta is not JSON-serialisable (it is stored as jsonb)")


def _json_safe(value: object) -> bool:
    import json

    try:
        json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        return False
    return True


def sweep(
    gen: Generator,
    seeds: Iterable[int],
    difficulties: Sequence[int] = (1, 2, 3, 4, 5),
    subtypes: Sequence[str] | None = None,
) -> list[CheckReport]:
    """Run :func:`check_instance` across seeds x difficulties x subtypes."""
    chosen = subtypes or gen.subtypes
    reports: list[CheckReport] = []
    for subtype in chosen:
        spec = gen.templates.subtypes[subtype]
        lo, hi = spec.difficulty_range
        for difficulty in difficulties:
            if not lo <= difficulty <= hi:
                continue
            for seed in seeds:
                reports.append(check_instance(gen, seed, difficulty, subtype))
    return reports
