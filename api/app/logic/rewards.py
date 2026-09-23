"""Coin rewards (design doc 5.2) and the daily threshold / cap (4.4).

Every number comes from ``economy.yaml``. The functions are pure; the service
layer records the resulting transaction idempotently.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

from app.config.loader import economy

Slot = Literal[
    "new", "strengthen", "consolidate", "repeat", "challenge",
    "practice", "similar", "onboarding", "placement", "extern", "boss", "exam", "python",
]


@dataclass(frozen=True, slots=True)
class RewardInput:
    task_no: int
    difficulty: int
    attempt_no: int
    """Which attempt produced the correct answer (1 = first)."""
    hints_used: int = 0
    revealed_before_answer: bool = False
    faster_than_target: bool = False
    slot: Slot = "practice"
    code_verified: bool | None = None
    """``None`` for tasks without code; ``False`` when the answer matched but the
    student's program failed the hidden variant (7.5.2)."""


def difficulty_bucket(difficulty: int) -> int:
    """Column of the 5.2 table: 1–2 → 0, 3 → 1, 4–5 → 2."""
    if difficulty <= 2:
        return 0
    if difficulty == 3:
        return 1
    return 2


def base_reward(task_no: int, difficulty: int) -> int:
    cfg = economy()
    return cfg.base_reward[cfg.level_of(task_no)][difficulty_bucket(difficulty)]


def attempt_multiplier(attempt_no: int) -> float:
    mods = economy().modifiers
    if attempt_no <= 1:
        return mods.first_attempt
    if attempt_no == 2:
        return mods.second_attempt
    return mods.later_attempts


def reward(inp: RewardInput) -> int:
    """Coins for a correct answer, before the daily cap is applied.

    Multipliers compound and the result is rounded up (5.2); the speed bonus is
    added afterwards and only to a non-zero reward, so it never rescues a task
    that earned nothing.
    """
    mods = economy().modifiers
    if inp.revealed_before_answer:
        return 0
    attempt = attempt_multiplier(inp.attempt_no)
    if attempt == 0:
        return 0
    if inp.slot == "challenge":
        coins = mods.challenge_fixed
    else:
        value = base_reward(inp.task_no, inp.difficulty) * attempt
        if inp.hints_used > 0:
            value *= mods.hint_used
        if inp.slot == "repeat":
            value *= mods.repeat_slot
        # Round half-cents away before ceil so 8 * 1.5 stays 12, not 13.
        coins = math.ceil(round(value, 6))
    if inp.code_verified is False:
        coins = math.ceil(round(coins * mods.unverified_code_share, 6))
    if coins > 0 and inp.faster_than_target:
        coins += mods.fast_bonus
    return coins


def xp_for(inp: RewardInput, correct: bool) -> int:
    """XP rewards volume and never burns (4.5): base value for a solve, 2 for trying.

    Unlike coins it keeps counting after the cap and in exams (decision D‑016).
    """
    if not correct:
        return 2
    return base_reward(inp.task_no, inp.difficulty)


@dataclass(frozen=True, slots=True)
class CapResult:
    credited: int
    capped: int
    """Coins that were earned but not credited because the cap was reached."""


def apply_cap(earned_today: int, amount: int) -> CapResult:
    """Credit at most up to the daily cap (4.4). After the cap: free practice."""
    cap = economy().day.cap
    room = max(0, cap - earned_today)
    credited = min(room, amount)
    return CapResult(credited=credited, capped=amount - credited)


def threshold_for(easy_day: bool) -> int:
    day = economy().day
    return day.easy_day_threshold if easy_day else day.threshold


def feedback_bonus(bonuses_today: int) -> int:
    mods = economy().modifiers
    return mods.feedback_bonus if bonuses_today < mods.feedback_bonus_per_day else 0


def rank_for(xp: int) -> tuple[str, int | None]:
    """Current rank name and the XP needed for the next one (``None`` at the top)."""
    ranks = economy().ranks
    current = ranks[0]
    following: int | None = None
    for i, rank in enumerate(ranks):
        if xp >= rank.xp:
            current = rank
            following = ranks[i + 1].xp if i + 1 < len(ranks) else None
    return current.name, following
