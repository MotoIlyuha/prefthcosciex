"""Pydantic-validated loading of the YAML configs under ``app/config``.

Everything a methodologist or product owner may tune — prices, rewards, floors,
bands — lives in YAML and is validated here at startup. A malformed file stops
the service from booting rather than producing wrong coin balances.

The admin panel can override individual values without a deploy; overrides are
stored in the ``config_overrides`` table and merged on top by :func:`apply_overrides`.
"""

from __future__ import annotations

import copy
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

CONFIG_DIR = Path(__file__).resolve().parent

Level = Literal["B", "P", "V", "V2"]
Band = Literal["A", "B", "C"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Modifiers(_Strict):
    first_attempt: float
    second_attempt: float
    later_attempts: float
    hint_used: float
    revealed_before_answer: float
    repeat_slot: float
    fast_bonus: int
    challenge_fixed: int
    feedback_bonus: int
    feedback_bonus_per_day: int
    unverified_code_share: float


class DayRules(_Strict):
    threshold: int = Field(gt=0)
    cap: int = Field(gt=0)
    easy_day_threshold: int = Field(gt=0)
    day_starts_at_hour: int = Field(ge=0, le=23)
    similar_per_subtype_per_day: int = Field(ge=0)

    @model_validator(mode="after")
    def _ordered(self) -> DayRules:
        if not self.easy_day_threshold <= self.threshold <= self.cap:
            raise ValueError("expected easy_day_threshold <= threshold <= cap")
        return self


class Prices(_Strict):
    hint: dict[Level, int]
    hints_per_instance: int
    reveal: dict[Level, int]
    free_reveals_per_day: int
    floor_base: int
    floor_step: int
    exam_full: int
    exam_half: int
    exam_block: int
    free_full_exams_per_month: int
    max_exam_tickets: int
    freeze: int
    restore_base: int
    restore_step: int
    restore_window_hours: int
    cosmetics_min: int
    cosmetics_max: int
    free_full_exams_in_may: int

    def floor(self, no: int) -> int:
        """Price of floor ``n``: 150 + 25·n (design doc 5.3)."""
        return self.floor_base + self.floor_step * no


class StreakRules(_Strict):
    freeze_every_days: int
    max_freezes: int
    vacation_days_per_month: int
    easy_days_per_week: int
    milestones: list[int]


class Rank(_Strict):
    name: str
    xp: int


class Health(_Strict):
    spent_to_earned_min: float
    spent_to_earned_max: float
    max_average_balance: int
    reveal_after_error_min: float
    reveal_after_error_max: float


class Cosmetic(_Strict):
    id: str
    kind: Literal["theme", "frame", "sticker"]
    title: str
    price: int


class Safety(_Strict):
    ticket_compensation: int


class Economy(_Strict):
    season_id: str
    levels: dict[Level, list[int]]
    base_reward: dict[Level, list[int]]
    modifiers: Modifiers
    day: DayRules
    prices: Prices
    cosmetics: list[Cosmetic]
    streak: StreakRules
    safety: Safety
    ranks: list[Rank]
    health: Health

    @model_validator(mode="after")
    def _complete(self) -> Economy:
        covered = sorted(t for tasks in self.levels.values() for t in tasks)
        if covered != list(range(1, 28)):
            raise ValueError("levels must assign each of the 27 tasks exactly once")
        for level, row in self.base_reward.items():
            if len(row) != 3:
                raise ValueError(f"base_reward.{level} needs three values")
        if [r.xp for r in self.ranks] != sorted(r.xp for r in self.ranks):
            raise ValueError("ranks must be ordered by XP")
        low, high = self.prices.cosmetics_min, self.prices.cosmetics_max
        for item in self.cosmetics:
            if not low <= item.price <= high:
                raise ValueError(f"cosmetic {item.id} costs outside {low}..{high}")
        if len({c.id for c in self.cosmetics}) != len(self.cosmetics):
            raise ValueError("cosmetic ids must be unique")
        return self

    def level_of(self, task_no: int) -> Level:
        for level, tasks in self.levels.items():
            if task_no in tasks:
                return level
        raise KeyError(task_no)


class Floor(_Strict):
    #: Called ``number`` in YAML: a bare ``no`` key parses as boolean False in YAML 1.1.
    number: int
    title: str
    tasks: list[int]
    python: str


class ExternRules(_Strict):
    tasks: int
    difficulty: int
    attempts_per_day: int


class BossRules(_Strict):
    tasks: int
    difficulty: int
    pass_needed: int


class Floors(_Strict):
    season_id: str
    floors: list[Floor]
    required_floors: dict[Band, list[int]]
    extern: ExternRules
    boss: BossRules

    @model_validator(mode="after")
    def _thirteen(self) -> Floors:
        if [f.number for f in self.floors] != list(range(1, 14)):
            raise ValueError("expected floors 1..13 in order")
        return self

    def floor_of_task(self, task_no: int) -> int:
        """First floor (excluding the final review floor) that teaches a task."""
        for floor in self.floors[:-1]:
            if task_no in floor.tasks:
                return floor.number
        return 13


class TaskInfo(_Strict):
    title: str
    level: Literal["Б", "П", "В"]
    points: int
    minutes: int
    software: bool


class BandInfo(_Strict):
    title: str
    range: tuple[int, int]
    core: list[int]
    bonus: list[int]


class BandWeight(_Strict):
    core: float
    bonus: float
    other: float
    focus: float


class Curriculum(_Strict):
    season_id: str
    tasks: dict[int, TaskInfo]
    score_scale: dict[int, int]
    bands: dict[Band, BandInfo]
    band_weight: BandWeight
    learning_cost: dict[int, float]
    code_recheck_tasks: list[int]

    @model_validator(mode="after")
    def _complete(self) -> Curriculum:
        if sorted(self.tasks) != list(range(1, 28)):
            raise ValueError("curriculum must describe all 27 tasks")
        if sum(t.points for t in self.tasks.values()) != 29:
            raise ValueError("the exam totals 29 primary points")
        if sorted(self.learning_cost) != list(range(1, 28)):
            raise ValueError("learning_cost must cover all 27 tasks")
        return self


def _read(name: str) -> dict[str, Any]:
    data = yaml.safe_load((CONFIG_DIR / name).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{name}: expected a mapping")
    return data


_overrides: dict[str, dict[str, Any]] = {}


def apply_overrides(section: str, patch: dict[str, Any]) -> None:
    """Install an admin override (a nested dict merged over the YAML) and revalidate."""
    candidate = dict(_overrides)
    candidate[section] = patch
    # Validate before accepting, so a bad override never reaches the live config.
    _build(section, candidate.get(section, {}))
    _overrides[section] = patch
    economy.cache_clear()
    floors.cache_clear()
    curriculum.cache_clear()


def clear_overrides() -> None:
    _overrides.clear()
    economy.cache_clear()
    floors.cache_clear()
    curriculum.cache_clear()


def _deep_merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def _build(section: str, patch: dict[str, Any]) -> BaseModel:
    match section:
        case "economy":
            return Economy.model_validate(_deep_merge(_read("economy.yaml"), patch))
        case "floors":
            return Floors.model_validate(_deep_merge(_read("floors.yaml"), patch))
        case "curriculum":
            return Curriculum.model_validate(_deep_merge(_read("curriculum.yaml"), patch))
    raise KeyError(section)


@lru_cache(maxsize=1)
def economy() -> Economy:
    result = _build("economy", _overrides.get("economy", {}))
    assert isinstance(result, Economy)
    return result


@lru_cache(maxsize=1)
def floors() -> Floors:
    result = _build("floors", _overrides.get("floors", {}))
    assert isinstance(result, Floors)
    return result


@lru_cache(maxsize=1)
def curriculum() -> Curriculum:
    result = _build("curriculum", _overrides.get("curriculum", {}))
    assert isinstance(result, Curriculum)
    return result


def validate_all() -> None:
    """Called at startup: a broken config must stop the service from booting."""
    economy()
    floors()
    curriculum()
