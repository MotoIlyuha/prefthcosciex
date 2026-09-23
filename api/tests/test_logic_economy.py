"""Rewards, cap, ranks and the three-profile simulation (design doc 5)."""

from __future__ import annotations

import pytest

from app.config.loader import apply_overrides, clear_overrides, economy
from app.logic.rewards import (
    RewardInput,
    apply_cap,
    base_reward,
    feedback_bonus,
    rank_for,
    reward,
    threshold_for,
    xp_for,
)
from tests.economy_sim import PROFILES, simulate


def test_typical_day_example_from_the_doc() -> None:
    """5.2: three mandatory dailies Б+П+П at first try give 12 + 18 + 18 = 48."""
    day = [RewardInput(1, 1, 1), RewardInput(11, 2, 1), RewardInput(15, 1, 1)]
    assert [reward(r) for r in day] == [12, 18, 18]


@pytest.mark.parametrize(
    ("task", "difficulty", "expected"),
    [(1, 1, 8), (1, 3, 10), (1, 5, 14), (17, 2, 12), (17, 3, 15), (17, 4, 20),
     (21, 1, 18), (24, 3, 22), (25, 5, 30), (26, 2, 30), (27, 3, 36), (27, 5, 45)],
)
def test_base_reward_table(task: int, difficulty: int, expected: int) -> None:
    assert base_reward(task, difficulty) == expected


def test_attempt_multipliers() -> None:
    assert reward(RewardInput(4, 3, 1)) == 15
    assert reward(RewardInput(4, 3, 2)) == 10
    assert reward(RewardInput(4, 3, 3)) == 0, "the third attempt closes the task with an error"


def test_hint_and_reveal() -> None:
    assert reward(RewardInput(4, 3, 1, hints_used=1)) == 11  # ceil(15 * 0.7)
    assert reward(RewardInput(4, 3, 1, revealed_before_answer=True)) == 0


def test_speed_bonus_is_additive_and_never_rescues_zero() -> None:
    assert reward(RewardInput(4, 3, 1, faster_than_target=True)) == 17
    assert reward(RewardInput(4, 3, 3, faster_than_target=True)) == 0


def test_repeat_and_challenge() -> None:
    assert reward(RewardInput(15, 3, 1, slot="repeat")) == 14  # ceil(22.5 * 0.6)
    assert reward(RewardInput(24, 5, 1, slot="challenge")) == 40
    assert reward(RewardInput(24, 5, 3, slot="challenge")) == 0


def test_unverified_code_halves_the_reward() -> None:
    """7.5.2: the answer matched but the program failed the hidden variant."""
    full = reward(RewardInput(17, 3, 1, code_verified=True))
    half = reward(RewardInput(17, 3, 1, code_verified=False))
    assert full == 23 and half == 12


def test_cap_and_threshold() -> None:
    assert apply_cap(0, 50).credited == 50
    result = apply_cap(110, 18)
    assert (result.credited, result.capped) == (10, 8)
    assert apply_cap(120, 40).credited == 0
    assert threshold_for(easy_day=False) == 30
    assert threshold_for(easy_day=True) == 10


def test_feedback_bonus_limit() -> None:
    assert [feedback_bonus(n) for n in range(5)] == [2, 2, 2, 0, 0]


def test_xp_counts_every_attempt() -> None:
    assert xp_for(RewardInput(4, 3, 3), correct=True) == 10
    assert xp_for(RewardInput(4, 3, 1), correct=False) == 2


def test_ranks() -> None:
    assert rank_for(0) == ("Байт", 500)
    assert rank_for(499) == ("Байт", 500)
    assert rank_for(500) == ("Килобайт", 2000)
    assert rank_for(20_000) == ("Терабайт", None)


def test_floor_prices() -> None:
    prices = economy().prices
    assert prices.floor(2) == 200
    assert prices.floor(12) == 450


def test_overrides_revalidate_and_apply() -> None:
    try:
        apply_overrides("economy", {"day": {"threshold": 25}})
        assert economy().day.threshold == 25
        with pytest.raises(ValueError):
            apply_overrides("economy", {"day": {"threshold": 500}})
        assert economy().day.threshold == 25, "a rejected override must not leak in"
    finally:
        clear_overrides()
    assert economy().day.threshold == 30


@pytest.mark.parametrize("profile", PROFILES, ids=lambda p: p.name)
def test_economy_sim(profile: object) -> None:
    """5.4: the simulated profiles reproduce the doc's figures within 15%.

    Weekly income is compared relatively. Net balance is compared as a share of
    weekly income, because a relative tolerance on a figure near zero (+25) is not
    meaningful — a 4-coin difference would read as a 16% miss (decision D‑019).
    """
    from tests.economy_sim import Profile

    assert isinstance(profile, Profile)
    income, net = simulate(profile)
    assert abs(income - profile.target_income_week) <= 0.15 * profile.target_income_week
    assert abs(net - profile.target_net_week) <= 0.15 * profile.target_income_week
    assert net > 0, "every profile must accumulate slowly, never hit a wall (5.4)"
