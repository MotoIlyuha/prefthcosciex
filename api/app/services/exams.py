"""Exam mode (design doc 8): full / half / block, KEGE-style answer sheet.

Answers are saved without feedback; everything is checked on finish. A finished
exam updates the skill model with weight ×1.5 (6.1) and opens every reveal for
free. The training mode can be paused, costs nothing and changes nothing: it is
not an exam for the forecast, the arbiter or the curator (decision D‑022).
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from egegen.checkers import check
from egegen.core.types import AnswerKind, derive_seed
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.loader import economy
from app.core.errors import ApiError, conflict, not_found
from app.db.models import Attempt, Exam, ExamAnswer, Instance, User
from app.logic import exam as rules
from app.logic import skills as skill_logic
from app.logic.timeutil import month_key, study_day
from app.services import events
from app.services import instances as inst_service
from app.services import skills as skill_service
from app.services import wallet as wallet_service
from app.services.curators import notify_curators
from app.services.notify import schedule

GRACE = timedelta(seconds=30)
"""Answers in flight when the timer hits zero are still accepted."""


def exam_difficulty(task_no: int) -> int:
    return 4 if economy().level_of(task_no) in ("V", "V2") else 3


async def _free_full_left(session: AsyncSession, user: User) -> int:
    day = study_day(user.tz)
    month = month_key(day)
    limit = (
        economy().prices.free_full_exams_in_may
        if day.month == 5
        else economy().prices.free_full_exams_per_month
    )
    used = await session.scalar(
        select(func.count())
        .select_from(Exam)
        .where(
            Exam.user_id == user.id,
            Exam.kind == "full",
            Exam.paid_with == "free",
            func.to_char(Exam.started_at, "YYYY-MM") == month,
        )
    )
    return max(0, limit - int(used or 0))


async def offer(session: AsyncSession, user: User) -> dict[str, Any]:
    wallet = await wallet_service.wallet_for_update(session, user.id)
    prices = economy().prices
    free_left = await _free_full_left(session, user)
    await session.commit()
    return {
        "formats": [
            {"kind": "full", "tasks": 27, "minutes": 235, "price": prices.exam_full},
            {"kind": "half", "tasks": 15, "minutes": 60, "price": prices.exam_half},
            {"kind": "block", "tasks": 5, "minutes": "20–30", "price": prices.exam_block},
        ],
        "free_full_left": free_left,
        "tickets": wallet.exam_tickets,
        "balance": wallet.balance,
    }


async def start(
    session: AsyncSession,
    user: User,
    kind: str,
    *,
    task_no: int | None = None,
    training: bool = False,
    idempotency_key: str | None = None,
) -> Exam:
    if kind not in ("full", "half", "block"):
        raise ApiError(422, "bad_kind", "Формат: full, half или block")
    active = await session.scalar(
        select(Exam).where(Exam.user_id == user.id, Exam.finished_at.is_(None)).limit(1)
    )
    if active is not None:
        if await _expire_if_needed(session, user, active):
            active = None
        else:
            raise conflict(
                "exam_in_progress", "Сначала завершите начатый экзамен", exam_id=active.id
            )
    block: tuple[int, ...] = ()
    if kind == "block":
        if task_no is None or not 1 <= task_no <= 27:
            raise ApiError(422, "bad_task", "Для блока выберите задание 1–27")
        block = rules.block_tasks_for_topic(task_no)
    fmt = rules.exam_format(cast(rules.Kind, kind), block)
    now = datetime.now(UTC)
    exam = Exam(
        user_id=user.id,
        kind=kind,
        training=training,
        started_at=now,
        meta={"block_task": task_no} if kind == "block" else {},
    )
    session.add(exam)
    await session.flush()

    if training:
        exam.paid_with = "training"
    elif kind == "full" and await _free_full_left(session, user) > 0:
        exam.paid_with = "free"
    else:
        wallet = await wallet_service.wallet_for_update(session, user.id)
        if kind == "full" and wallet.exam_tickets > 0:
            wallet.exam_tickets -= 1
            exam.paid_with = "ticket"
        else:
            await wallet_service.move(
                session,
                user.id,
                -fmt.price,
                reason=f"exam_{kind}",
                key=f"exam:{user.id}:{idempotency_key or exam.id}",
                ref_type="exam",
                ref_id=exam.id,
            )
            exam.paid_with = "coins"
    exam.deadline_at = now + timedelta(minutes=fmt.minutes)
    exam.meta = {**exam.meta, "minutes": fmt.minutes, "paused_s": 0}
    day = study_day(user.tz)
    for position, t in enumerate(fmt.tasks, start=1):
        seed = derive_seed(user.id, day, t, exam.id, slot=f"exam:{position}")
        row = await inst_service.create(
            session,
            user_id=user.id,
            task_no=t,
            subtype=None,
            difficulty=exam_difficulty(t),
            seed=seed,
            context="exam",
            slot="exam",
            exam_id=exam.id,
            expires_at=exam.deadline_at + GRACE if not training else None,
        )
        row.state = "issued"
        row.issued_at = now
        session.add(ExamAnswer(exam_id=exam.id, position=position, task_no=t, instance_id=row.id))
    await events.track(
        session,
        "exam_started",
        user.id,
        {"kind": kind, "training": training, "paid_with": exam.paid_with},
    )
    await session.commit()
    return exam


async def owned(session: AsyncSession, user: User, exam_id: int) -> Exam:
    exam = await session.get(Exam, exam_id)
    if exam is None or exam.user_id != user.id:
        raise not_found("экзамен")
    return exam


def seconds_left(exam: Exam, now: datetime | None = None) -> int:
    if exam.finished_at is not None or exam.deadline_at is None:
        return 0
    moment = now or datetime.now(UTC)
    if exam.meta.get("paused_at"):
        moment = datetime.fromisoformat(exam.meta["paused_at"])
    return max(0, int((exam.deadline_at - moment).total_seconds()))


async def _lock(session: AsyncSession, exam: Exam) -> None:
    """Re-read the exam row FOR UPDATE: a save, a pause and the finish (also the one
    triggered by the deadline) serialize, so no answer lands after the grading."""
    await session.refresh(exam, with_for_update=True)


async def _expire_if_needed(session: AsyncSession, user: User, exam: Exam) -> bool:
    """The timer keeps running when the app is closed (8): finish on the deadline."""
    if exam.finished_at is not None or exam.meta.get("paused_at"):
        return False
    if exam.deadline_at is not None and datetime.now(UTC) > exam.deadline_at + GRACE:
        await finish(session, user, exam)
        return True
    return False


async def view(session: AsyncSession, user: User, exam: Exam) -> dict[str, Any]:
    await _expire_if_needed(session, user, exam)
    answers = list(
        await session.scalars(
            select(ExamAnswer).where(ExamAnswer.exam_id == exam.id).order_by(ExamAnswer.position)
        )
    )
    rows = {
        r.id: r
        for r in await session.scalars(
            select(Instance).where(Instance.id.in_([a.instance_id for a in answers]))
        )
    }
    finished = exam.finished_at is not None
    sheet = []
    for a in answers:
        row = rows[a.instance_id]
        item: dict[str, Any] = {
            "position": a.position,
            "task_no": a.task_no,
            "answered": a.answer_raw is not None and a.answer_raw != "",
            "answer": a.answer_raw,
            "time_spent_s": a.time_spent_s,
            "instance": inst_service.public(row),
        }
        if finished:
            item.update(correct=a.is_correct, points=a.points)
        sheet.append(item)
    return {
        "id": exam.id,
        "kind": exam.kind,
        "training": exam.training,
        "started_at": exam.started_at,
        "deadline_at": exam.deadline_at,
        "seconds_left": seconds_left(exam),
        "paused": bool(exam.meta.get("paused_at")),
        "finished": finished,
        "sheet": sheet,
        "result": await result(session, exam) if finished else None,
    }


async def save_answer(
    session: AsyncSession, user: User, exam: Exam, position: int, raw: str, time_spent_s: int
) -> dict[str, Any]:
    await _lock(session, exam)
    if await _expire_if_needed(session, user, exam) or exam.finished_at is not None:
        raise conflict("exam_finished", "Экзамен уже завершён")
    if exam.meta.get("paused_at"):
        raise conflict("exam_paused", "Экзамен на паузе")
    answer = await session.get(ExamAnswer, (exam.id, position), with_for_update=True)
    if answer is None:
        raise not_found("задание экзамена")
    answer.answer_raw = raw.strip()[:4000]
    answer.time_spent_s = max(answer.time_spent_s, min(max(0, time_spent_s), 4 * 3600))
    await session.commit()
    return {"position": position, "saved": True, "seconds_left": seconds_left(exam)}


async def pause(session: AsyncSession, exam: Exam, paused: bool) -> dict[str, Any]:
    if not exam.training:
        raise conflict("no_pause", "Пауза есть только в тренировочном режиме")
    await _lock(session, exam)
    if exam.finished_at is not None:
        raise conflict("exam_finished", "Экзамен уже завершён")
    now = datetime.now(UTC)
    meta = dict(exam.meta)
    if paused and not meta.get("paused_at"):
        meta["paused_at"] = now.isoformat()
    elif not paused and meta.get("paused_at"):
        stopped = datetime.fromisoformat(meta.pop("paused_at"))
        pause_s = int((now - stopped).total_seconds())
        meta["paused_s"] = int(meta.get("paused_s", 0)) + pause_s
        if exam.deadline_at is not None:
            exam.deadline_at += timedelta(seconds=pause_s)
    exam.meta = meta
    await session.commit()
    return {"paused": bool(meta.get("paused_at")), "seconds_left": seconds_left(exam)}


def correct_parts(row: Instance, raw: str) -> int:
    """Correct numbers in a two-number answer (26, 27 give a point for each, 2.2)."""
    verdict = check(cast(AnswerKind, row.answer_kind), raw, row.answer, dict(row.checker_options))
    if verdict.correct:
        return 2 if row.answer_kind == "two_ints" else 1
    if row.answer_kind != "two_ints":
        return 0
    got = re.findall(r"[+-]?\d+", raw)
    exp = re.findall(r"[+-]?\d+", row.answer)
    if len(got) != 2 or len(exp) != 2:
        return 0
    return sum(1 for g, e in zip(got, exp, strict=True) if int(g) == int(e))


async def finish(session: AsyncSession, user: User, exam: Exam) -> dict[str, Any]:
    await _lock(session, exam)
    if exam.finished_at is not None:
        return await result(session, exam)
    now = datetime.now(UTC)
    exam.finished_at = now
    answers = list(
        await session.scalars(
            select(ExamAnswer).where(ExamAnswer.exam_id == exam.id).order_by(ExamAnswer.position)
        )
    )
    rows = {
        r.id: r
        for r in await session.scalars(
            select(Instance).where(Instance.id.in_([a.instance_id for a in answers]))
        )
    }
    per_task: dict[int, int] = {}
    day = study_day(user.tz)
    for a in answers:
        row = rows[a.instance_id]
        raw = a.answer_raw or ""
        parts = correct_parts(row, raw) if raw else 0
        a.points = rules.score_answer(a.task_no, parts) if raw else 0
        full_marks = a.points == (2 if row.answer_kind == "two_ints" else 1)
        a.is_correct = bool(raw) and full_marks
        per_task[a.task_no] = per_task.get(a.task_no, 0) + a.points
        row.state = "solved" if a.is_correct else "failed"
        row.solved_at = now if a.is_correct else None
        row.attempts_count = 1
        session.add(
            Attempt(
                instance_id=row.id,
                user_id=user.id,
                no=1,
                answer_raw=raw[:4000],
                is_correct=a.is_correct,
                time_spent_s=a.time_spent_s,
            )
        )
        if not exam.training:
            srow = await skill_service.row_for(session, user.id, row.subtype_id, row.task_no)
            state = skill_logic.update(
                skill_service.to_state(srow),
                difficulty=row.difficulty,
                correct=a.is_correct,
                attempt_no=1,
                hints_used=0,
                time_ratio=a.time_spent_s / max(1, row.target_seconds) if a.time_spent_s else None,
                today=day,
                exam=True,
            )
            skill_service.write_state(srow, state)
    if exam.kind == "block":
        primary = sum(a.points for a in answers)
        exam.primary_score, exam.test_score = primary, 0
        exam.per_task = {str(a.position): a.points for a in answers}
    else:
        score = rules.total(per_task, cast(rules.Kind, exam.kind))
        exam.primary_score, exam.test_score = score.primary, score.test
        exam.per_task = {str(t): p for t, p in sorted(per_task.items())}
        exam.meta = {**exam.meta, "lost_most": list(score.lost_most)}
    await events.track(
        session,
        "exam_finished",
        user.id,
        {"kind": exam.kind, "training": exam.training, "primary": exam.primary_score},
    )
    if not exam.training:
        payload = {
            "primary": exam.primary_score,
            "test": exam.test_score or None,
            "link": str(exam.id),
        }
        await schedule(session, user.id, "exam_checked", payload, dedupe=f"exam_checked:{exam.id}")
        await notify_curators(
            session,
            user,
            "cur_exam",
            {**payload, "dedupe_suffix": f"exam{exam.id}"},
            min_access="progress",
        )
    await session.commit()
    return await result(session, exam)


async def result(session: AsyncSession, exam: Exam) -> dict[str, Any]:
    answers = list(
        await session.scalars(
            select(ExamAnswer).where(ExamAnswer.exam_id == exam.id).order_by(ExamAnswer.position)
        )
    )
    previous = await session.execute(
        select(Exam.id, Exam.finished_at, Exam.primary_score)
        .where(
            Exam.user_id == exam.user_id,
            Exam.kind == exam.kind,
            Exam.training.is_(False),
            Exam.finished_at.is_not(None),
            Exam.id != exam.id,
        )
        .order_by(Exam.finished_at.desc())
        .limit(10)
    )
    return {
        "primary": exam.primary_score,
        "test": exam.test_score,
        "per_position": [
            {
                "position": a.position,
                "task_no": a.task_no,
                "points": a.points,
                "correct": a.is_correct,
                "time_spent_s": a.time_spent_s,
                "instance_id": a.instance_id,
            }
            for a in answers
        ],
        "lost_most": exam.meta.get("lost_most", []),
        "history": [
            {"id": i, "finished_at": f, "primary": p} for i, f, p in reversed(previous.all())
        ],
        "reveals_free": True,
    }


async def history(session: AsyncSession, user: User) -> list[dict[str, Any]]:
    rows = await session.scalars(
        select(Exam).where(Exam.user_id == user.id).order_by(Exam.started_at.desc()).limit(50)
    )
    return [
        {
            "id": e.id,
            "kind": e.kind,
            "training": e.training,
            "started_at": e.started_at,
            "finished_at": e.finished_at,
            "primary": e.primary_score,
            "test": e.test_score,
            "paid_with": e.paid_with,
        }
        for e in rows
    ]
