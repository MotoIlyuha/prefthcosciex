"""Answer submission — design doc 5.2, 5.6, 6.1, 6.4, 7.4, 7.5, 11.4.

One call does everything a correct or wrong answer implies: checks the answer,
records the attempt, re-checks the student's program on the hidden variant, pays
coins up to the daily cap, moves the streak, updates the skill model and reports
the confidence shift. The server is the only source of truth for all of it.
"""

from __future__ import annotations

import hashlib
from collections.abc import Awaitable, Callable
from dataclasses import replace
from datetime import UTC, date, datetime
from typing import Any, cast

from egegen.checkers import check
from egegen.core.types import AnswerKind
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.loader import curriculum, economy
from app.core.errors import conflict
from app.db.models import Attempt, DailyStats, Instance, User
from app.logic import skills as skill_logic
from app.logic.rewards import RewardInput, apply_cap, reward, threshold_for, xp_for
from app.logic.timeutil import study_day
from app.services import events
from app.services import skills as skill_service
from app.services import wallet as wallet_service
from app.services.curators import notify_curators
from app.services.daily import stats_for
from app.services.runner_client import RunnerUnavailableError
from app.services.runner_client import run as run_code
from app.services.streaks import mark_threshold

MAX_ATTEMPTS = 3
SINGLE_ATTEMPT = frozenset({"placement", "extern", "boss"})
"""Tests of level take one answer per task: a second try would measure nothing."""
CLOSED = frozenset({"solved", "failed", "revealed", "expired"})

METHOD_LABELS: dict[int, str] = {
    1: "Сопоставил степени вершин схемы и строк таблицы",
    2: "Перебрал наборы и перестановки столбцов",
    4: "Нарисовал двоичное дерево кодов",
    5: "Записал алгоритм функцией и перебрал N",
    6: "Нашёл вершины и посчитал точки",
    7: "Перевёл всё в биты и посчитал по формуле",
    8: "Перебрал слова через product",
    10: "Перебрал длину маски от 32 вниз",
    11: "Посчитал бит на символ и байт на пароль",
    12: "Смоделировал замены в Python",
    13: "Посчитал динамикой f(a, b)",
    14: "Вычислил значение и перевёл в систему",
    15: "Перебрал параметр A и проверил формулу для всех x",
    19: "Применил шаблон W1/L1/W2/L2",
    20: "Применил шаблон W1/L1/W2/L2",
    21: "Применил шаблон W1/L1/W2/L2",
}
DISTRACTORS = ("Посмотрел ответ у друга", "Угадал", "Нашёл похожую задачу в интернете")

OnClose = Callable[[AsyncSession, User, Instance, bool], Awaitable[dict[str, Any]]]
_close_hooks: dict[str, OnClose] = {}


def on_close(context: str) -> Callable[[OnClose], OnClose]:
    """Register what happens when an instance of a context (placement, extern…) closes."""

    def wrap(fn: OnClose) -> OnClose:
        _close_hooks[context] = fn
        return fn

    return wrap


def min_seconds(task_no: int) -> int:
    """Faster than this is physically implausible (7.5.3): ~11 % of the spec time.

    For task 15 (3 minutes) that is 20 seconds, the doc's own example.
    """
    if task_no == 0:
        return 5
    return max(10, round(0.11 * curriculum().tasks[task_no].minutes * 60))


def method_options(task_no: int) -> list[str]:
    correct = METHOD_LABELS.get(task_no, "Решил по методу из карточки")
    return [correct, *DISTRACTORS]


def _program_output(row: Instance, text: str) -> str:
    """A program prints one pair per line; the answer field takes «a b, c d» (7.4)."""
    if row.answer_kind == "pairs_list":
        return ", ".join(line.strip() for line in text.splitlines() if line.strip())
    return text.strip()


def _matches(row: Instance, printed: str, expected: str) -> bool:
    verdict = check(
        cast(AnswerKind, row.answer_kind),
        _program_output(row, printed),
        _program_output(row, expected),
        dict(row.checker_options),
    )
    return verdict.correct


HIDDEN_TRIES = 6
"""Hidden variants tried until the reference solution runs on one (a graph task's
variant may name its vertices differently from the visible statement)."""


def _hidden_seeds(row: Instance) -> list[int]:
    seeds = [row.hidden_seed]
    for k in range(1, HIDDEN_TRIES):
        digest = hashlib.blake2b(f"hidden|{row.hidden_seed}|{k}".encode(), digest_size=8)
        seeds.append(int.from_bytes(digest.digest(), "big") & 0x7FFF_FFFF_FFFF_FFFF)
    return seeds


async def _hidden_files(
    row: Instance, seed: int, data_names: list[str], build_deferred: bool
) -> dict[str, bytes] | None:
    """Data files of one hidden variant, ``None`` if they do not match the visible ones."""
    from app.services.bigfiles import build_deferred_for_seed
    from app.services.instances import generate

    hidden = await generate(row.task_no, seed, row.difficulty, row.subtype_id)
    files: dict[str, bytes] = {}
    for asset in hidden.assets:
        if asset.kind == "svg":
            continue
        if asset.deferred:
            if not build_deferred:
                raise _DeferredError
            files[asset.name] = await build_deferred_for_seed(row, seed, asset.name)
        else:
            files[asset.name] = asset.content
    return files if sorted(files) == sorted(data_names) else None


class _DeferredError(Exception):
    """File B of task 27 is needed: only the worker builds it."""


async def verify_code(row: Instance, code: str, *, build_deferred: bool = False) -> str:
    """Re-check the student's program on a hidden variant (7.5.2).

    The hidden variant has different data files of the same format. The expected
    output is what this instance's own reference solution prints on those files:
    it carries the visible statement's parameters, so an honest program agrees with
    it and one with the answer typed in does not. When no hidden variant fits (or
    the task has no files, like 16 and 25), the program runs on the visible data and
    must compute the answer without containing it.

    Returns ``ok``, ``mismatch``, ``error`` (the program crashed) or ``pending``
    (file B of task 27 must be built by the worker, or the runner is down).
    """
    from app.services.instances import read_asset

    data_names = [a["name"] for a in row.assets if a.get("kind") != "svg"]
    literal = len(row.answer) >= 2 and row.answer in code
    try:
        chosen: tuple[dict[str, bytes], str] | None = None
        if data_names and row.reference_code:
            fallback: tuple[dict[str, bytes], str] | None = None
            for seed in _hidden_seeds(row):
                files = await _hidden_files(row, seed, data_names, build_deferred)
                if files is None:
                    continue
                reference = await run_code(row.reference_code, files)
                expected = reference.stdout.strip()
                if not reference.ok or not expected:
                    continue
                if _matches(row, expected, row.answer):
                    fallback = fallback or (files, expected)  # not discriminating
                    continue
                chosen = (files, expected)
                break
            chosen = chosen or fallback
        if chosen is None:
            if literal:
                return "mismatch"
            visible = {name: await read_asset(row, name) for name in data_names}
            chosen = (visible, row.answer)
        files, expected = chosen
        result = await run_code(code, files)
    except _DeferredError:
        return "pending"
    except RunnerUnavailableError:
        return "pending"
    if not result.ok:
        return "error"
    return "ok" if _matches(row, result.stdout.strip(), expected) else "mismatch"


async def confidence_value(session: AsyncSession, user_id: int, task_no: int) -> float:
    states = await skill_service.all_states(session, user_id)
    mine = {sid: st for sid, (t, st) in states.items() if t == task_no}
    return skill_logic.confidence(task_no, mine, datetime.now(UTC).date()).value


async def submit(
    session: AsyncSession,
    user: User,
    row: Instance,
    raw: str,
    *,
    time_spent_s: int,
    code: str | None = None,
    method_choice: str | None = None,
) -> dict[str, Any]:
    if row.context == "exam":
        raise conflict("exam_instance", "Ответы экзамена сохраняются в режиме экзамена")
    now = datetime.now(UTC)
    if row.expires_at is not None and row.expires_at < now and row.state not in CLOSED:
        row.state = "expired"
        await session.commit()
    if row.state in CLOSED:
        raise conflict("closed", "Эта задача уже закрыта", state=row.state)

    verdict = check(cast(AnswerKind, row.answer_kind), raw, row.answer, dict(row.checker_options))
    if not verdict.correct and verdict.reason:
        # A malformed answer is a formatting slip, not an attempt (7.4).
        return {"status": "format_error", "message": verdict.reason, "counted": False}

    fast = time_spent_s < min_seconds(row.task_no)
    needs_method = (
        verdict.correct
        and fast
        and not row.requires_code
        and row.context not in ("onboarding", "placement")
    )
    if needs_method and method_choice is None:
        return {
            "status": "method_check",
            "question": "Каким способом решали?",
            "options": method_options(row.task_no),
            "counted": False,
        }
    method_ok = not needs_method or method_choice == method_options(row.task_no)[0]

    row.attempts_count += 1
    attempt_no = row.attempts_count
    day = study_day(user.tz)
    stats = await stats_for(session, user.id, day)
    stats.time_spent_s += max(0, min(time_spent_s, 3 * 3600))
    confidence_before = await confidence_value(session, user.id, row.task_no)

    verify_status = "n/a"
    if verdict.correct and row.task_no in curriculum().code_recheck_tasks:
        verify_status = await verify_code(row, code) if code else "no_code"
    attempt = Attempt(
        instance_id=row.id,
        user_id=user.id,
        no=attempt_no,
        answer_raw=raw[:4000],
        is_correct=verdict.correct,
        time_spent_s=time_spent_s,
        hints_used=row.hints_used,
        code_snapshot=(code or row.last_code),
        verify_status=verify_status,
        method_check={"asked": needs_method, "choice": method_choice, "ok": method_ok},
    )
    session.add(attempt)
    if code:
        row.last_code = code
    row.issued_at = row.issued_at or now

    result: dict[str, Any] = {
        "status": "correct" if verdict.correct else "wrong",
        "attempt_no": attempt_no,
        "attempts_left": max(
            0, (1 if row.context in SINGLE_ATTEMPT else MAX_ATTEMPTS) - attempt_no
        ),
        "coins": 0,
        "capped": 0,
        "verify_status": verify_status,
        "counted": True,
    }

    max_attempts = 1 if row.context in SINGLE_ATTEMPT else MAX_ATTEMPTS
    closed = verdict.correct or attempt_no >= max_attempts
    coins = 0
    if verdict.correct:
        row.state = "solved"
        row.solved_at = now
        coins, capped = await _pay(
            session,
            user,
            row,
            stats,
            attempt,
            attempt_no,
            time_spent_s,
            verify_status,
            method_ok,
            fast,
        )
        result["coins"], result["capped"] = coins, capped
        stats.tasks_done += 1
    else:
        row.state = "failed" if closed else "attempted"
        if row.state == "failed":
            stats.tasks_done += 1

    xp = xp_for(RewardInput(row.task_no, row.difficulty, attempt_no), verdict.correct)
    rank, rank_up = await wallet_service.add_xp(session, user.id, xp)
    stats.xp += xp
    result.update({"xp": xp, "rank": rank, "rank_up": rank_up})

    if closed and row.task_no:
        weight = 1.0
        if not method_ok:
            weight = 0.5
        if verify_status in ("mismatch", "no_code", "error"):
            weight = 0.3  # "mastery +0.3 instead of +1" (7.5.2)
        srow = await skill_service.row_for(session, user.id, row.subtype_id, row.task_no)
        updated = skill_logic.update(
            skill_service.to_state(srow),
            difficulty=row.difficulty,
            correct=verdict.correct,
            attempt_no=attempt_no,
            hints_used=row.hints_used,
            time_ratio=time_spent_s / max(1, row.target_seconds),
            today=day,
            weight=weight,
        )
        skill_service.write_state(srow, updated)

    await _threshold_and_cap(session, user, stats, day, result)

    not_ideal = not verdict.correct or row.hints_used > 0 or time_spent_s > 2 * row.target_seconds
    result["ask_reason"] = bool(not_ideal and row.task_no)
    if verdict.correct and verify_status in ("mismatch", "no_code", "error"):
        result["verdict_text"] = "Ответ верный, метод не подтверждён"
    elif verdict.correct and verify_status == "ok":
        result["verdict_text"] = "Решено надёжно"
    elif verdict.correct:
        result["verdict_text"] = "Верно"
    else:
        result["verdict_text"] = "Не то. Ещё попытка?" if not closed else "Задача закрыта с ошибкой"
    if not method_ok:
        result["method_note"] = "Бонус за скорость не начислен: способ решения не подтверждён"

    if closed and row.task_no:
        confidence_after = await confidence_value(session, user.id, row.task_no)
        result["confidence"] = {
            "task_no": row.task_no,
            "before": round(confidence_before),
            "after": round(confidence_after),
        }
    if closed and row.context in _close_hooks:
        result["context_result"] = await _close_hooks[row.context](
            session, user, row, verdict.correct
        )

    await events.track(
        session,
        "attempt",
        user.id,
        {
            "task_no": row.task_no,
            "correct": verdict.correct,
            "attempt_no": attempt_no,
            "context": row.context,
            "verify_status": verify_status,
        },
    )
    await session.commit()

    if verify_status == "pending":
        from app.services.jobs import enqueue

        await enqueue("recheck_code", attempt.id)
    return result


async def _pay(
    session: AsyncSession,
    user: User,
    row: Instance,
    stats: DailyStats,
    attempt: Attempt,
    attempt_no: int,
    time_spent_s: int,
    verify_status: str,
    method_ok: bool,
    fast: bool,
) -> tuple[int, int]:
    """Credit the reward up to the daily cap; returns (credited, cut by the cap)."""
    code_verified: bool | None = None
    if row.task_no in curriculum().code_recheck_tasks:
        code_verified = verify_status == "ok"
    slot = row.slot if row.slot in ("repeat", "challenge") else "practice"
    amount = reward(
        RewardInput(
            task_no=row.task_no,
            difficulty=row.difficulty,
            attempt_no=attempt_no,
            hints_used=row.hints_used,
            revealed_before_answer=row.revealed,
            faster_than_target=method_ok and not fast and time_spent_s < row.target_seconds,
            slot=slot,  # type: ignore[arg-type]
            code_verified=code_verified,
        )
    )
    if row.context in ("placement", "extern", "boss"):
        amount = 0  # tests of level are not a way to farm coins
    if row.slot == "similar" and not row.meta.get("paid", True):
        amount = 0  # more than three similar tasks per subtype per day (5.6)
    capped = apply_cap(stats.coins_earned, amount)
    if capped.credited > 0:
        await wallet_service.move(
            session,
            user.id,
            capped.credited,
            reason="task_reward",
            key=f"reward:{row.id}",
            ref_type="instance",
            ref_id=row.id,
            meta={"attempt_no": attempt_no, "verify_status": verify_status},
        )
    stats.coins_earned += capped.credited
    stats.coins_capped += capped.capped
    attempt.coins = capped.credited
    return capped.credited, capped.capped


async def _threshold_and_cap(
    session: AsyncSession, user: User, stats: DailyStats, day: date, result: dict[str, Any]
) -> None:
    if not stats.threshold_met and stats.coins_earned >= threshold_for(stats.easy_day):
        stats.threshold_met = True
        milestones = await mark_threshold(session, user.id, day)
        result["threshold_met"] = True
        result["milestones"] = milestones
        for value in milestones:
            await notify_curators(
                session, user, "cur_milestone", {"streak": value, "dedupe_suffix": f"streak{value}"}
            )
        await events.track(session, "threshold_met", user.id, {"coins": stats.coins_earned})
    if stats.coins_earned >= economy().day.cap:
        result["cap_reached"] = True
        if result.get("coins", 0) > 0:
            # The answer that crossed the cap is the one that reports it (15.3).
            await events.track(session, "cap_reached", user.id, {"capped": result["capped"]})


async def finish_recheck(session: AsyncSession, attempt_id: int) -> str:
    """Worker side of 7.5.2 for checks that could not run inline (file B of 27).

    A confirmed program tops the reward up to the full rate, within the cap of the
    day it was earned; a failed one leaves the half already paid.
    """
    attempt = await session.get(Attempt, attempt_id, with_for_update=True)
    if attempt is None or attempt.verify_status != "pending":
        return attempt.verify_status if attempt else "missing"
    row = await session.get(Instance, attempt.instance_id)
    user = await session.get(User, attempt.user_id)
    if row is None or user is None or not attempt.code_snapshot:
        return "missing"
    status = await verify_code(row, attempt.code_snapshot, build_deferred=True)
    if status == "pending":
        return status  # the runner is still down: ARQ retries the job
    attempt.verify_status = status
    if status == "ok" and attempt.is_correct:
        slot = row.slot if row.slot in ("repeat", "challenge") else "practice"
        full = reward(
            RewardInput(
                task_no=row.task_no,
                difficulty=row.difficulty,
                attempt_no=attempt.no,
                hints_used=attempt.hints_used,
                revealed_before_answer=row.revealed,
                slot=slot,  # type: ignore[arg-type]
                code_verified=True,
            )
        )
        day = study_day(user.tz, attempt.created_at)
        stats = await stats_for(session, user.id, day)
        top_up = apply_cap(stats.coins_earned, max(0, full - attempt.coins))
        if top_up.credited > 0:
            await wallet_service.move(
                session,
                user.id,
                top_up.credited,
                reason="task_reward",
                key=f"reward-verified:{row.id}",
                ref_type="instance",
                ref_id=row.id,
                meta={"verify_status": "ok"},
            )
            stats.coins_earned += top_up.credited
            attempt.coins += top_up.credited
        srow = await skill_service.row_for(session, user.id, row.subtype_id, row.task_no)
        state = skill_service.to_state(srow)
        # The first update counted with weight 0.3; add the rest of a full success
        # to the rating only — it is the same attempt, not a new one.
        boosted = skill_logic.update(
            state,
            difficulty=row.difficulty,
            correct=True,
            attempt_no=attempt.no,
            hints_used=attempt.hints_used,
            time_ratio=None,
            today=day,
            weight=0.7,
        )
        skill_service.write_state(srow, replace(state, rating=boosted.rating))
    await session.commit()
    return status
