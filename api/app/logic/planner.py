"""Daily plan (design doc 6.3): three mandatory slots and two bonus ones.

Pure function of the user's skill state; the worker calls it at 05:00 local time
and the result is stored in ``daily_plans``.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date

from app.config.loader import floors
from app.logic.skills import (
    SkillState,
    confidence,
    d_to_difficulty,
    learning_priority,
)

MAX_MANDATORY_SECONDS = 20 * 60
TEASER_WEIGHT = 0.3
FLOW_OFFSET = 147.0
"""rating − D = 147 gives P(correct) ≈ 0.7, the flow zone (6.3.4)."""

REASON_FLAGS: dict[str, str] = {
    "no_method": "method_card",
    "misread": "condition_checklist",
    "code_bug": "code_template",
    "careless": "check_step",
    "time": "sprint",
    "format": "format_hint",
    "forgot": "cheat_sheet",
}
EASIER_AFTER = frozenset({"no_method", "misread"})
"""Reasons after which the next instance of the subtype is one step easier.

The design doc lowers difficulty only after "no_method"; the build prompt's
acceptance test also requires it after "misread" (decision D‑018)."""


@dataclass(frozen=True, slots=True)
class SubtypeInfo:
    subtype: str
    task_no: int
    target_seconds: int
    requires_code: bool
    beta: bool = False


@dataclass(frozen=True, slots=True)
class PlanItem:
    slot: str
    task_no: int
    subtype: str
    difficulty: int
    mandatory: bool
    target_seconds: int
    flags: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PlanInput:
    today: date
    band: str
    unlocked_floors: frozenset[int]
    subtypes: Sequence[SubtypeInfo]
    skills: dict[str, SkillState] = field(default_factory=dict)
    focus_tasks: tuple[int, ...] = ()
    yesterday_tasks: tuple[int, ...] = ()
    easy_day: bool = False
    challenge_enabled: bool = False
    python_exercise_due: bool = False


def _tasks_open(unlocked: frozenset[int]) -> tuple[set[int], set[int]]:
    """Tasks on unlocked floors, and tasks on the next locked floor (the teaser)."""
    cfg = floors()
    open_tasks: set[int] = set()
    for floor in cfg.floors:
        if floor.number in unlocked:
            open_tasks.update(floor.tasks)
    locked = [f for f in cfg.floors if f.number not in unlocked]
    teaser = set(locked[0].tasks) - open_tasks if locked else set()
    return open_tasks, teaser


def _scaled_seconds(info: SubtypeInfo, difficulty: int) -> int:
    return max(30, round(info.target_seconds * (1 + 0.15 * (difficulty - 3))))


def pick_difficulty(state: SkillState, today: date, *, new_slot: bool) -> int:
    level = d_to_difficulty(state.effective_rating(today) - FLOW_OFFSET)
    if new_slot:
        level -= 1
    if state.reasons and state.reasons[-1] in EASIER_AFTER:
        level -= 1
    return max(1, min(5, level))


def flags_for(state: SkillState) -> tuple[str, ...]:
    if not state.reasons:
        return ()
    flag = REASON_FLAGS.get(state.reasons[-1])
    return (flag,) if flag else ()


def plan(inp: PlanInput) -> list[PlanItem]:
    today = inp.today
    open_tasks, teaser = _tasks_open(inp.unlocked_floors)
    by_task: dict[int, list[SubtypeInfo]] = {}
    for info in inp.subtypes:
        by_task.setdefault(info.task_no, []).append(info)

    def state_of(subtype: str) -> SkillState:
        return inp.skills.get(subtype, SkillState())

    task_conf = {
        task: confidence(task, {s.subtype: state_of(s.subtype) for s in infos}, today).value
        for task, infos in by_task.items()
    }

    scored: list[tuple[float, SubtypeInfo]] = []
    for info in inp.subtypes:
        if info.task_no not in open_tasks and info.task_no not in teaser:
            continue
        priority = learning_priority(
            info.task_no, task_conf[info.task_no], inp.band, inp.focus_tasks
        )
        if info.task_no in teaser:
            priority *= TEASER_WEIGHT
        state = state_of(info.subtype)
        if state.next_review is not None and state.next_review <= today:
            priority += 0.05 * (today - state.next_review).days + 0.05
        scored.append((priority, info))
    scored.sort(key=lambda pair: (-pair[0], pair[1].subtype))

    def item(
        info: SubtypeInfo, slot: str, *, mandatory: bool, difficulty: int | None = None
    ) -> PlanItem:
        state = state_of(info.subtype)
        level = difficulty or pick_difficulty(state, today, new_slot=slot == "new")
        return PlanItem(
            slot=slot,
            task_no=info.task_no,
            subtype=info.subtype,
            difficulty=level,
            mandatory=mandatory,
            target_seconds=_scaled_seconds(info, level),
            flags=flags_for(state),
        )

    if inp.easy_day:
        # "Лёгкий день" (4.2): one Б-level task, threshold drops to 10.
        easy = [info for _, info in scored if info.task_no <= 10 and not info.beta]
        if not easy:
            easy = [info for _, info in scored if not info.beta]
        return [item(easy[0], "new", mandatory=True, difficulty=1)] if easy else []

    chosen: list[PlanItem] = []
    used_tasks: set[int] = set()
    budget = MAX_MANDATORY_SECONDS

    def eligible(info: SubtypeInfo, *, mastery_band: tuple[float, float] | None) -> bool:
        if info.beta or info.task_no in used_tasks:
            return False
        state = state_of(info.subtype)
        mastery = state.mastery(today)
        if info.task_no in inp.yesterday_tasks and mastery > 0.3:
            return False
        if mastery_band is not None and not mastery_band[0] <= mastery < mastery_band[1]:
            return False
        level = pick_difficulty(state, today, new_slot=False)
        return _scaled_seconds(info, level) <= budget

    def take(slot: str, band: tuple[float, float] | None, pool: Sequence[SubtypeInfo]) -> bool:
        nonlocal budget
        for info in pool:
            if eligible(info, mastery_band=band):
                entry = item(info, slot, mandatory=True)
                chosen.append(entry)
                used_tasks.add(info.task_no)
                budget -= entry.target_seconds
                return True
        return False

    ranked = [info for _, info in scored]
    review_queue = sorted(
        (
            info
            for info in ranked
            if (st := state_of(info.subtype)).next_review is not None and st.next_review <= today
        ),
        key=lambda info: state_of(info.subtype).next_review or today,
    )

    if inp.python_exercise_due:
        chosen.append(PlanItem("python", 0, "py.minimum", 1, True, 300, ("python_minimum",)))
        budget -= 300
    else:
        take("new", (0.0, 0.5), ranked) or take("new", None, ranked)
    take("strengthen", (0.5, 0.8), ranked) or take("strengthen", None, ranked)
    take("consolidate", None, review_queue) or take("consolidate", None, ranked)

    # At least one task without code, so a phone session can rest the eyes (6.3.5).
    if chosen and all(
        next((i.requires_code for i in inp.subtypes if i.subtype == c.subtype), False)
        for c in chosen
        if c.slot != "python"
    ):
        light = next(
            (
                i
                for i in ranked
                if not i.requires_code and i.task_no not in used_tasks and not i.beta
            ),
            None,
        )
        if light is not None:
            replaced = chosen.pop()
            used_tasks.discard(replaced.task_no)
            chosen.append(item(light, replaced.slot, mandatory=True))
            used_tasks.add(light.task_no)

    _include_focus(chosen, inp, ranked, used_tasks, item)
    _reach_minimum_coins(chosen, inp)

    # Bonus: "Повтор" from the review queue, then "Вызов".
    for info in review_queue:
        if info.task_no not in used_tasks:
            chosen.append(item(info, "repeat", mandatory=False))
            used_tasks.add(info.task_no)
            break
    else:
        for info in ranked:
            if info.task_no not in used_tasks and not info.beta:
                chosen.append(item(info, "repeat", mandatory=False))
                used_tasks.add(info.task_no)
                break

    if inp.challenge_enabled:
        strong = [
            info
            for info in ranked
            if state_of(info.subtype).mastery(today) >= 0.8 and info.task_no not in used_tasks
        ]
        hard = [
            info for info in inp.subtypes if info.task_no >= 24 and info.task_no not in used_tasks
        ]
        # Beta generators are allowed here and only here (16.5).
        pool = strong or sorted(hard, key=lambda i: i.subtype)
        if pool:
            chosen.append(item(pool[0], "challenge", mandatory=False, difficulty=5))
    return chosen


def _include_focus(
    chosen: list[PlanItem],
    inp: PlanInput,
    ranked: Sequence[SubtypeInfo],
    used_tasks: set[int],
    make: object,
) -> None:
    """Make sure a curator's focus topic actually shows up (9.3).

    band_weight 1.5 alone cannot lift an expensive topic past a cheap one under the
    3.2 formula (15 costs four hours, task 1 one), so without this the focus would
    be invisible for weeks. The focus task takes over the "strengthen" slot when it
    fits the 20-minute budget (decision D‑020).
    """
    if not inp.focus_tasks or any(c.task_no in inp.focus_tasks for c in chosen):
        return
    candidate = next((i for i in ranked if i.task_no in inp.focus_tasks and not i.beta), None)
    if candidate is None:
        return
    assert callable(make)
    entry = make(candidate, "strengthen", mandatory=True)
    assert isinstance(entry, PlanItem)
    for index, current in enumerate(chosen):
        if current.slot == "strengthen":
            others = sum(c.target_seconds for c in chosen if c.mandatory and c is not current)
            if others + entry.target_seconds <= MAX_MANDATORY_SECONDS:
                used_tasks.discard(current.task_no)
                chosen[index] = entry
                used_tasks.add(candidate.task_no)
            return


MIN_MANDATORY_COINS = 40
"""Mandatory slots must be worth ≥ 40 coins at first attempt, so the 30-coin threshold
survives one mistake (4.2)."""


def expected_coins(items: Sequence[PlanItem]) -> int:
    from app.logic.rewards import RewardInput, reward

    return sum(
        reward(RewardInput(i.task_no, i.difficulty, 1, slot="practice"))
        for i in items
        if i.mandatory and i.slot != "python"
    )


def _reach_minimum_coins(chosen: list[PlanItem], inp: PlanInput) -> None:
    """Raise difficulty of the non-"new" mandatory slots until the plan pays ≥ 40.

    The "new" slot is left alone: the first contact with a topic must succeed
    (6.3.4). Each step moves a task at most two levels above its flow difficulty,
    and never over the 20-minute budget.
    """
    for _ in range(4):
        if expected_coins(chosen) >= MIN_MANDATORY_COINS:
            return
        bumped = False
        for index, entry in enumerate(chosen):
            if not entry.mandatory or entry.slot in ("new", "python") or entry.difficulty >= 5:
                continue
            info = next((i for i in inp.subtypes if i.subtype == entry.subtype), None)
            if info is None:
                continue
            raised = PlanItem(
                entry.slot,
                entry.task_no,
                entry.subtype,
                entry.difficulty + 1,
                True,
                _scaled_seconds(info, entry.difficulty + 1),
                entry.flags,
            )
            others = sum(c.target_seconds for c in chosen if c.mandatory and c is not entry)
            if others + raised.target_seconds > MAX_MANDATORY_SECONDS:
                continue
            chosen[index] = raised
            bumped = True
            if expected_coins(chosen) >= MIN_MANDATORY_COINS:
                return
        if not bumped:
            return


def mandatory_seconds(items: Sequence[PlanItem]) -> int:
    return sum(i.target_seconds for i in items if i.mandatory)
