"""Simulation of the three player profiles from design doc 5.4.

Run directly for a report (``uv run python tests/economy_sim.py``); the test
``test_economy_sim`` asserts the simulated weekly figures stay within 15% of the
doc's targets. Income is computed as an expectation over first/second-try success
rates using the real reward function, so any change to ``economy.yaml`` is
reflected here.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.config.loader import economy
from app.logic.rewards import RewardInput, reward


@dataclass(frozen=True)
class Task:
    task_no: int
    difficulty: int
    slot: str = "practice"


@dataclass(frozen=True)
class Profile:
    name: str
    tasks: tuple[Task, ...]
    first_try: float
    second_try: float
    feedback_answers: int
    weekly_spend: dict[str, float]
    target_income_week: int
    target_net_week: int


def expected_task_income(task: Task, first: float, second: float) -> float:
    one = reward(RewardInput(task.task_no, task.difficulty, 1, slot=task.slot))  # type: ignore[arg-type]
    two = reward(RewardInput(task.task_no, task.difficulty, 2, slot=task.slot))  # type: ignore[arg-type]
    return first * one + second * two


def daily_income(profile: Profile) -> float:
    cfg = economy()
    raw = sum(expected_task_income(t, profile.first_try, profile.second_try) for t in profile.tasks)
    raw += profile.feedback_answers * cfg.modifiers.feedback_bonus
    return min(raw, cfg.day.cap)


def weekly_spend(profile: Profile) -> float:
    prices = economy().prices
    unit = {
        "floor": prices.floor(4),        # a mid-game floor, 250 coins
        "reveal": prices.reveal["P"],
        "half_exam": prices.exam_half,
        "full_exam": prices.exam_full,
        "freeze": prices.freeze,
    }
    return sum(unit[item] * count for item, count in profile.weekly_spend.items())


PROFILES = (
    Profile(
        name="Минималист (порог)",
        tasks=(Task(1, 2), Task(4, 2), Task(11, 2)),
        first_try=0.55,
        second_try=0.30,
        feedback_answers=0,
        # A floor every ten days is 0.7 floors a week, plus two paid reveals.
        weekly_spend={"floor": 0.7, "reveal": 2},
        target_income_week=230,
        target_net_week=25,
    ),
    Profile(
        name="Типичный",
        tasks=(
            Task(4, 3), Task(12, 3), Task(15, 3),
            Task(11, 3, "repeat"), Task(24, 5, "challenge"),
        ),
        # A typical student clears the daily challenge only about half the time,
        # which is what brings income into the doc's 70-100 coins a day.
        first_try=0.60,
        second_try=0.20,
        feedback_answers=1,
        # "этаж/нед (250–300)": a floor a week, at the upper end of that range.
        weekly_spend={"floor": 1.2, "reveal": 4, "half_exam": 1, "freeze": 1},
        target_income_week=600,
        target_net_week=130,
    ),
    Profile(
        name="Сильный (кэп)",
        tasks=(
            Task(24, 5, "challenge"), Task(25, 5), Task(26, 5), Task(27, 5), Task(23, 5),
        ),
        first_try=0.90,
        second_try=0.08,
        feedback_answers=0,
        weekly_spend={"full_exam": 1},
        target_income_week=840,
        target_net_week=690,
    ),
)


def simulate(profile: Profile) -> tuple[float, float]:
    income = 7 * daily_income(profile)
    return income, income - weekly_spend(profile)


def report() -> str:
    lines = [f"{'Профиль':<22}{'доход/нед':>12}{'цель':>8}{'итог':>10}{'цель':>8}"]
    for profile in PROFILES:
        income, net = simulate(profile)
        lines.append(
            f"{profile.name:<22}{income:>12.0f}{profile.target_income_week:>8}"
            f"{net:>10.0f}{profile.target_net_week:>8}"
        )
    return "\n".join(lines)


if __name__ == "__main__":
    print(report())
