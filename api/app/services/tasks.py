"""Everything a student does with an open task besides answering it (11.4).

Opening, hints, the full solution, "why was it hard", similar tasks, the draft and
server-side code runs. Answers live in :mod:`app.services.answers`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from egegen.core.cards import get_card
from egegen.core.types import derive_seed
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.loader import economy, floors
from app.core.errors import ApiError, conflict, forbidden
from app.db.models import DifficultyFeedback, Exam, Instance, Subtype, User
from app.logic import skills as skill_logic
from app.logic.planner import flags_for, pick_difficulty
from app.logic.rewards import PYTHON_TRACK, RewardInput, feedback_bonus, reward
from app.logic.timeutil import study_day
from app.services import events
from app.services import instances as inst_service
from app.services import skills as skill_service
from app.services import wallet as wallet_service
from app.services.daily import stats_for, unlocked_floors
from app.services.runner_client import RunnerUnavailableError
from app.services.runner_client import run as run_code

OPEN_STATES = frozenset({"planned", "issued", "attempted"})
MAX_DRAFT_CHARS = 20_000
CHECKLIST = (
    "Что именно нужно найти: наибольшее, наименьшее, количество?",
    "Какие ограничения на числа или символы есть в условии?",
    "В каком виде записать ответ?",
)
REACTIONS: dict[str, dict[str, str]] = {
    "no_method": {"action": "method_card", "note": "Следующая задача этого типа будет проще."},
    "misread": {"action": "checklist", "note": "В следующий раз — три вопроса до ответа."},
    "code_bug": {"action": "code_template", "note": "Проверь код на маленьком примере."},
    "careless": {"action": "check_step", "note": "Перед отправкой — шаг «проверь ответ»."},
    "time": {"action": "sprint", "note": "Потренируй скорость: 3 задачи подряд с таймером."},
    "format": {"action": "format_hint", "note": "Формат ответа — над полем ввода."},
    "forgot": {"action": "cheat_sheet", "note": "Шпаргалка и повтор завтра."},
    "other": {"action": "moderation", "note": "Спасибо, методист посмотрит."},
}


def level_of(task_no: int) -> str:
    return "B" if task_no == PYTHON_TRACK else economy().level_of(task_no)


def hint_price(task_no: int) -> int:
    return economy().prices.hint[level_of(task_no)]  # type: ignore[index]


def reveal_price(task_no: int) -> int:
    return economy().prices.reveal[level_of(task_no)]  # type: ignore[index]


def expected_coins(row: Instance) -> int:
    if row.context in ("placement", "extern", "boss", "exam"):
        return 0
    slot = row.slot if row.slot in ("repeat", "challenge") else "practice"
    return reward(RewardInput(row.task_no, row.difficulty, 1, slot=slot))  # type: ignore[arg-type]


async def _exam_finished(session: AsyncSession, row: Instance) -> bool:
    if row.exam_id is None:
        return False
    exam = await session.get(Exam, row.exam_id)
    return exam is not None and exam.finished_at is not None


async def view(session: AsyncSession, user: User, row: Instance) -> dict[str, Any]:
    """The task screen. Opening a planned task moves it to ``issued`` (12.4)."""
    now = datetime.now(UTC)
    if row.state in OPEN_STATES and row.expires_at is not None and row.expires_at < now:
        row.state = "expired"
    if row.state == "planned":
        row.state = "issued"
        row.issued_at = now
        await events.track(
            session,
            "instance_issued",
            user.id,
            {"task_no": row.task_no, "context": row.context, "slot": row.slot},
        )
    stats = await stats_for(session, user.id, study_day(user.tz))
    await session.commit()
    data = inst_service.public(row)
    in_exam = row.context == "exam" and not await _exam_finished(session, row)
    data.update(
        {
            "reward": expected_coins(row),
            "hint_price": None if in_exam else hint_price(row.task_no),
            "hints_left": 0
            if in_exam
            else max(
                0,
                min(economy().prices.hints_per_instance, len(row.solution_steps)) - row.hints_used,
            ),
            "hints": row.solution_steps[: row.hints_used],
            "reveal_price": None if in_exam else reveal_price(row.task_no),
            "free_reveal_available": (
                stats.free_reveals_used < economy().prices.free_reveals_per_day
            ),
            "checklist": list(CHECKLIST) if "condition_checklist" in row.flags else [],
            "code_rule": (
                "Ответ засчитывается полностью, если твоя программа выдаёт верный ответ и "
                "на скрытом варианте. Совпал только ответ — половина монет."
                if row.requires_code or row.task_no in (16, 17, 23, 24, 25, 26, 27)
                else ""
            ),
        }
    )
    if row.state == "revealed" or (row.revealed and row.state not in OPEN_STATES):
        data["solution"] = solution(row)
    return data


def solution(row: Instance) -> dict[str, Any]:
    return {
        "answer": row.answer,
        "steps": row.solution_steps,
        "reference_code": row.reference_code,
        "method_card_id": row.method_card_id,
    }


async def hint(session: AsyncSession, user: User, row: Instance) -> dict[str, Any]:
    if row.context in ("exam", "placement", "extern", "boss"):
        raise forbidden("В этом режиме подсказок нет")
    if row.state not in OPEN_STATES:
        raise conflict("closed", "Задача закрыта")
    limit = min(economy().prices.hints_per_instance, len(row.solution_steps))
    if row.hints_used >= limit:
        raise conflict("no_more_hints", "Подсказки закончились — остался разбор")
    price = hint_price(row.task_no)
    number = row.hints_used + 1
    await wallet_service.move(
        session,
        user.id,
        -price,
        reason="hint",
        key=f"hint:{row.id}:{number}",
        ref_type="instance",
        ref_id=row.id,
    )
    row.hints_used = number
    await events.track(session, "hint", user.id, {"task_no": row.task_no, "no": number})
    await session.commit()
    return {"hint": row.solution_steps[number - 1], "hints_used": number, "price": price}


async def reveal(session: AsyncSession, user: User, row: Instance) -> dict[str, Any]:
    """Full solution with this instance's numbers (5.3). The day's first one is free."""
    if row.context in ("placement", "extern", "boss"):
        raise forbidden("Разбор откроется после завершения теста")
    exam_done = await _exam_finished(session, row)
    if row.context == "exam" and not exam_done:
        raise forbidden("Разборы откроются после завершения экзамена")
    if row.revealed:
        return {"solution": solution(row), "price": 0, "free": True}
    after_error = row.state in ("failed", "expired") or (row.context == "exam" and exam_done)
    price = 0
    free = False
    if row.context == "exam":
        free = True  # already paid for by the exam ticket (8)
    else:
        stats = await stats_for(session, user.id, study_day(user.tz))
        if after_error and stats.free_reveals_used < economy().prices.free_reveals_per_day:
            stats.free_reveals_used += 1
            free = True
        else:
            price = reveal_price(row.task_no)
            await wallet_service.move(
                session,
                user.id,
                -price,
                reason="reveal",
                key=f"reveal:{row.id}",
                ref_type="instance",
                ref_id=row.id,
            )
    row.revealed = True
    if row.state in ("failed", "expired"):
        row.state = "revealed"
    await events.track(
        session,
        "reveal",
        user.id,
        {"task_no": row.task_no, "after_error": after_error, "free": free},
    )
    await session.commit()
    return {"solution": solution(row), "price": price, "free": free}


async def feedback(
    session: AsyncSession, user: User, row: Instance, reason: str, free_text: str | None
) -> dict[str, Any]:
    """«Что было сложным?» (6.4): one tap, stored per subtype, small bonus."""
    if reason not in skill_logic.REASONS:
        raise ApiError(422, "bad_reason", "Неизвестная причина")
    if row.task_no == PYTHON_TRACK:
        raise conflict("not_applicable", "Для упражнений Python причины не собираем")
    exists = await session.scalar(
        select(DifficultyFeedback.id).where(
            DifficultyFeedback.instance_id == row.id, DifficultyFeedback.user_id == user.id
        )
    )
    if exists is not None:
        return {"bonus": 0, "reaction": REACTIONS[reason], "duplicate": True}
    session.add(
        DifficultyFeedback(
            instance_id=row.id,
            user_id=user.id,
            reason_code=reason,
            free_text=(free_text or "")[:1000] if reason == "other" else None,
        )
    )
    srow = await skill_service.row_for(session, user.id, row.subtype_id, row.task_no)
    skill_service.write_state(srow, skill_logic.add_reason(skill_service.to_state(srow), reason))
    day = study_day(user.tz)
    stats = await stats_for(session, user.id, day)
    bonus = feedback_bonus(stats.feedback_bonuses)
    if bonus:
        await wallet_service.move(
            session,
            user.id,
            bonus,
            reason="feedback_bonus",
            key=f"feedback:{row.id}",
            ref_type="instance",
            ref_id=row.id,
        )
        stats.feedback_bonuses += 1
    await events.track(
        session, "feedback_reason", user.id, {"task_no": row.task_no, "reason": reason}
    )
    await session.commit()
    reaction = dict(REACTIONS[reason])
    if reason in ("no_method", "forgot", "code_bug"):
        card = get_card(row.method_card_id)
        reaction["card_id"] = card.id
    return {"bonus": bonus, "reaction": reaction, "duplicate": False}


async def open_tasks(session: AsyncSession, user_id: int) -> set[int]:
    opened = await unlocked_floors(session, user_id)
    return {t for f in floors().floors if f.number in opened for t in f.tasks}


async def similar(
    session: AsyncSession,
    user: User,
    *,
    instance_id: int | None,
    task_no: int | None,
    subtype: str | None,
) -> Instance:
    """A fresh instance of the same kind (5.5: free and unlimited).

    It pays the usual rate, up to the cap and for at most three per subtype a day
    (5.6); beyond that it is pure practice.
    """
    difficulty: int | None = None
    if instance_id is not None:
        base = await inst_service.owned(session, instance_id, user.id)
        if base.context == "exam" and not await _exam_finished(session, base):
            raise forbidden("Во время экзамена похожих задач нет")
        task_no, subtype, difficulty = base.task_no, base.subtype_id, base.difficulty
    if task_no is None or not 1 <= task_no <= 27:
        raise ApiError(422, "bad_task", "Укажите задание от 1 до 27")
    if task_no not in await open_tasks(session, user.id):
        raise forbidden("Этаж с этим заданием ещё закрыт")
    if subtype is None:
        subtype = await _weakest_subtype(session, user.id, task_no)
    elif not await session.scalar(
        select(Subtype.id).where(Subtype.id == subtype, Subtype.task_no == task_no)
    ):
        raise ApiError(422, "bad_subtype", "Неизвестный подтип")
    srow = await skill_service.row_for(session, user.id, subtype, task_no)
    state = skill_service.to_state(srow)
    if difficulty is None:
        difficulty = pick_difficulty(state, study_day(user.tz), new_slot=False)
    day = study_day(user.tz)
    stats = await stats_for(session, user.id, day)
    counts = dict(stats.similar_counts or {})
    done = counts.get(subtype, 0)
    counts[subtype] = done + 1
    stats.similar_counts = counts
    serial = (
        await session.scalar(
            select(func.count())
            .select_from(Instance)
            .where(
                Instance.user_id == user.id,
                Instance.slot == "similar",
                Instance.task_no == task_no,
                Instance.created_at
                >= datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0),
            )
        )
        or 0
    )
    seed = derive_seed(user.id, day, task_no, int(serial) + 1, slot=f"similar:{subtype}:{done}")
    row = await inst_service.create(
        session,
        user_id=user.id,
        task_no=task_no,
        subtype=subtype,
        difficulty=difficulty,
        seed=seed,
        context="practice",
        slot="similar",
        tz=user.tz,
        flags=list(flags_for(state)),
    )
    row.meta = {**row.meta, "paid": done < economy().day.similar_per_subtype_per_day}
    await session.commit()
    return row


async def _weakest_subtype(session: AsyncSession, user_id: int, task_no: int) -> str:
    subtypes = list(
        await session.scalars(
            select(Subtype.id).where(Subtype.task_no == task_no).order_by(Subtype.id)
        )
    )
    if not subtypes:
        raise ApiError(422, "bad_task", "Для задания нет подтипов")
    states = await skill_service.all_states(session, user_id)
    today = datetime.now(UTC).date()

    def mastery(sid: str) -> float:
        if sid not in states:
            return 0.5
        return states[sid][1].mastery(today)

    return min(subtypes, key=lambda s: (mastery(s), s))


async def save_draft(row: Instance, draft: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        k: str(v)[:MAX_DRAFT_CHARS]
        for k, v in draft.items()
        if k in ("answer", "code", "notes") and v is not None
    }
    row.draft = {**(row.draft or {}), **allowed}
    if "code" in allowed:
        row.last_code = allowed["code"]
    return row.draft


async def run(session: AsyncSession, user: User, row: Instance, code: str) -> dict[str, Any]:
    """Server-side run for weak devices (11.10): same files, same 10 s limit."""
    if len(code) > MAX_DRAFT_CHARS:
        raise ApiError(413, "code_too_long", "Программа слишком длинная")
    files = {
        a["name"]: await inst_service.read_asset(row, a["name"])
        for a in row.assets
        if a.get("kind") != "svg"
    }
    try:
        result = await run_code(code, files)
    except RunnerUnavailableError as exc:
        raise ApiError(
            503, "runner_unavailable", "Сервер запуска недоступен. Запусти код в браузере."
        ) from exc
    row.code_run_seen = True
    row.last_code = code
    await session.commit()
    return {
        "ok": result.ok,
        "stdout": result.stdout[-20_000:],
        "stderr": result.stderr[-5_000:],
        "exit_code": result.exit_code,
        "timed_out": result.timed_out,
        "duration_ms": result.duration_ms,
    }


async def mark_code_run(session: AsyncSession, row: Instance, code: str) -> None:
    """The browser (Pyodide) reports that the student ran the program at least once."""
    row.code_run_seen = True
    row.last_code = code[:MAX_DRAFT_CHARS]
    await session.commit()
