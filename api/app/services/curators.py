"""Curators (design doc 9): links, access levels, dashboard, nudges, focus, reports, league."""

from __future__ import annotations

import html
from datetime import UTC, date, datetime, timedelta
from typing import Any, cast

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.loader import curriculum
from app.core.errors import ApiError, conflict, forbidden, not_found
from app.core.security import random_token
from app.db.models import (
    Attempt,
    ConfidenceSnapshot,
    CuratorFocus,
    CuratorInvite,
    CuratorLink,
    DailyStats,
    DifficultyFeedback,
    Exam,
    Instance,
    Nudge,
    Streak,
    User,
    UserSettings,
    Wallet,
)
from app.logic import curator as rules
from app.logic import skills as skill_logic
from app.logic.rewards import threshold_for
from app.logic.timeutil import study_day, week_start
from app.services import events
from app.services import skills as skill_service
from app.services.notify import schedule
from app.settings import get_settings

ACCESS_ORDER: dict[str, int] = {"fact": 0, "progress": 1, "full": 2}


def invite_link(token: str) -> str:
    username = get_settings().telegram_bot_username or "bayt_bot"
    return f"https://t.me/{username}?start=cur_{token}"


async def _active_links_of_student(session: AsyncSession, student_id: int) -> list[CuratorLink]:
    return list(
        await session.scalars(
            select(CuratorLink).where(
                CuratorLink.student_id == student_id,
                CuratorLink.status.in_(("pending", "active")),
            )
        )
    )


async def notify_curators(
    session: AsyncSession,
    student: User,
    kind: str,
    payload: dict[str, Any],
    *,
    min_access: str = "fact",
) -> int:
    """Tell every active curator of ``student`` about an event (9.4)."""
    links = await session.scalars(
        select(CuratorLink).where(
            CuratorLink.student_id == student.id, CuratorLink.status == "active"
        )
    )
    sent = 0
    for link in links:
        if ACCESS_ORDER[link.access] < ACCESS_ORDER[min_access]:
            continue
        body = {"name": student.first_name or "Ученик", **payload, "link": str(student.id)}
        extra = payload.get("dedupe_suffix", "")
        row = await schedule(
            session,
            link.curator_id,
            kind,
            body,
            dedupe=f"{kind}:{link.curator_id}:{student.id}:{extra or date.today().isoformat()}",
            at=link.daily_digest_time if kind == "cur_digest" else None,
        )
        sent += row is not None
    return sent


async def create_invite(
    session: AsyncSession, student: User, role: str, username: str | None = None
) -> dict[str, Any]:
    if role not in ("parent", "tutor"):
        raise ApiError(422, "bad_role", "Роль: parent или tutor")
    if len(await _active_links_of_student(session, student.id)) >= rules.MAX_CURATORS_PER_STUDENT:
        raise conflict("too_many_curators", "У ученика может быть не больше двух кураторов")
    token = random_token(18)
    now = datetime.now(UTC)
    invite = CuratorInvite(
        token=token,
        student_id=student.id,
        role=role,
        created_at=now,
        expires_at=now + timedelta(hours=rules.INVITE_TTL_HOURS),
    )
    session.add(invite)
    delivered = False
    if username:
        target = await session.scalar(
            select(User).where(func.lower(User.username) == username.lstrip("@").lower())
        )
        if target is not None and target.id != student.id:
            # The bot can only write to people who already talked to it (9.1).
            delivered = (
                await schedule(
                    session,
                    target.id,
                    "cur_invite",
                    {"name": student.first_name or "Ученик", "link": f"cur_{token}"},
                    dedupe=f"cur_invite:{token}",
                )
                is not None
            )
    await session.commit()
    return {
        "token": token,
        "link": invite_link(token),
        "expires_at": invite.expires_at,
        "delivered_to_username": delivered,
    }


async def accept(session: AsyncSession, curator: User, token: str) -> dict[str, Any]:
    invite = await session.get(CuratorInvite, token, with_for_update=True)
    now = datetime.now(UTC)
    if invite is None or invite.used_by is not None or invite.expires_at < now:
        raise ApiError(410, "invite_expired", "Приглашение недействительно или истекло")
    if invite.student_id == curator.id:
        raise conflict("self_link", "Нельзя стать куратором самому себе")
    existing = await session.scalar(
        select(CuratorLink).where(
            CuratorLink.student_id == invite.student_id,
            CuratorLink.curator_id == curator.id,
            CuratorLink.status.in_(("pending", "active")),
        )
    )
    if existing is not None:
        invite.used_by = curator.id
        await session.commit()
        return {"link_id": existing.id, "status": existing.status}
    if len(await _active_links_of_student(session, invite.student_id)) >= (
        rules.MAX_CURATORS_PER_STUDENT
    ):
        raise conflict("too_many_curators", "У ученика уже два куратора")
    students = (
        await session.scalar(
            select(func.count())
            .select_from(CuratorLink)
            .where(CuratorLink.curator_id == curator.id, CuratorLink.status == "active")
        )
        or 0
    )
    if students >= rules.MAX_STUDENTS_PER_CURATOR:
        raise conflict("too_many_students", "Бесплатно — до 30 учеников")
    link = CuratorLink(
        student_id=invite.student_id,
        curator_id=curator.id,
        status="pending",
        access=rules.DEFAULT_ACCESS[invite.role],
        role=invite.role,
        invited_by=invite.student_id,
    )
    session.add(link)
    invite.used_by = curator.id
    await session.flush()
    await session.commit()
    return {"link_id": link.id, "status": link.status, "student_confirms_access": True}


async def link_for_student(session: AsyncSession, student: User, link_id: int) -> CuratorLink:
    link = await session.get(CuratorLink, link_id)
    if link is None or link.student_id != student.id or link.status == "revoked":
        raise not_found("куратор")
    return link


async def set_access(
    session: AsyncSession, student: User, link_id: int, access: str
) -> dict[str, Any]:
    """The student chooses (and later changes) what the curator sees (9.2)."""
    if access not in ACCESS_ORDER:
        raise ApiError(422, "bad_access", "Уровень: fact, progress или full")
    link = await link_for_student(session, student, link_id)
    became_active = link.status == "pending"
    link.access = access
    link.status = "active"
    if link.role == "parent":
        link.league_enabled = False
    if became_active:
        await events.track(
            session, "curator_linked", student.id, {"role": link.role, "access": access}
        )
    await session.commit()
    return {"link_id": link.id, "status": link.status, "access": link.access}


async def revoke(session: AsyncSession, user: User, link_id: int) -> None:
    """One tap from either side; the curator is told without a reason (9.1)."""
    link = await session.get(CuratorLink, link_id)
    if link is None or user.id not in (link.student_id, link.curator_id):
        raise not_found("связь")
    if link.status == "revoked":
        return
    link.status = "revoked"
    if user.id == link.student_id:
        await schedule(session, link.curator_id, "cur_revoked", {}, dedupe=f"cur_revoked:{link.id}")
    await events.track(
        session,
        "curator_revoked",
        user.id,
        {"by": "student" if user.id == link.student_id else "curator"},
    )
    await session.commit()


async def my_curators(session: AsyncSession, student: User) -> list[dict[str, Any]]:
    rows = await session.execute(
        select(CuratorLink, User)
        .join(User, User.id == CuratorLink.curator_id)
        .where(CuratorLink.student_id == student.id, CuratorLink.status != "revoked")
    )
    return [
        {
            "id": link.id,
            "name": cur.first_name,
            "username": cur.username,
            "role": link.role,
            "access": link.access,
            "status": link.status,
        }
        for link, cur in rows.all()
    ]


async def link_for_curator(session: AsyncSession, curator: User, student_id: int) -> CuratorLink:
    link = await session.scalar(
        select(CuratorLink).where(
            CuratorLink.curator_id == curator.id,
            CuratorLink.student_id == student_id,
            CuratorLink.status == "active",
        )
    )
    if link is None:
        raise not_found("ученик")
    return link


async def student_card(session: AsyncSession, student: User) -> dict[str, Any]:
    """Everything a curator could possibly see; :func:`rules.visible` trims it."""
    today = study_day(student.tz)
    streak = await session.get(Streak, student.id)
    wallet = await session.get(Wallet, student.id)
    stats_rows = list(
        await session.scalars(
            select(DailyStats)
            .where(DailyStats.user_id == student.id, DailyStats.date >= today - timedelta(days=29))
            .order_by(DailyStats.date)
        )
    )
    today_stats = next((s for s in stats_rows if s.date == today), None)
    states = await skill_service.all_states(session, student.id)
    by_task: dict[int, dict[str, skill_logic.SkillState]] = {}
    for sid, (task_no, st) in states.items():
        by_task.setdefault(task_no, {})[sid] = st
    confidences = [skill_logic.confidence(t, by_task.get(t, {}), today) for t in range(1, 28)]
    total_attempts = sum(c.attempts for c in confidences)
    last_exam = await _recent_exam_primary(session, student.id)
    fc = skill_logic.forecast(
        confidences, total_attempts=total_attempts, recent_exam_primary=last_exam
    )
    exams = await session.scalars(
        select(Exam)
        .where(Exam.user_id == student.id, Exam.finished_at.is_not(None), Exam.training.is_(False))
        .order_by(Exam.finished_at.desc())
        .limit(10)
    )
    reasons = await session.execute(
        select(DifficultyFeedback.reason_code, func.count())
        .where(DifficultyFeedback.user_id == student.id)
        .group_by(DifficultyFeedback.reason_code)
    )
    attempts = await session.execute(
        select(Attempt, Instance.task_no)
        .join(Instance, Instance.id == Attempt.instance_id)
        .where(Attempt.user_id == student.id, Instance.void.is_(False))
        .order_by(Attempt.created_at.desc())
        .limit(50)
    )
    return {
        "student_id": student.id,
        "name": student.first_name,
        "streak": {
            "current": streak.current if streak else 0,
            "best": streak.best if streak else 0,
        },
        "threshold_today": bool(today_stats and today_stats.threshold_met),
        "rank": wallet.rank if wallet else "",
        "coins_by_day": [
            {
                "date": s.date.isoformat(),
                "coins": s.coins_earned,
                "threshold": threshold_for(s.easy_day),
                "easy": s.easy_day,
                "vacation": s.vacation,
            }
            for s in stats_rows
        ],
        "confidence": [
            {"task_no": c.task_no, "value": c.value, "colour": skill_logic.colour(c.value)}
            for c in confidences
        ],
        "forecast": {"primary": fc.primary, "test": fc.test, "margin": fc.margin},
        "exams": [
            {
                "id": e.id,
                "kind": e.kind,
                "primary": e.primary_score,
                "test": e.test_score,
                "finished_at": e.finished_at,
            }
            for e in exams
        ],
        "subtypes": [
            {
                "subtype": sid,
                "task_no": t,
                "mastery": round(st.mastery(today) * 100, 1),
                "attempts": st.attempts,
            }
            for sid, (t, st) in sorted(states.items())
        ],
        # Codes only: the free text of "other" never leaves moderation (14.3).
        "reasons": {code: int(n) for code, n in reasons.all()},
        "attempts": [
            {
                "task_no": task_no,
                "answer": a.answer_raw,
                "correct": a.is_correct,
                "time_spent_s": a.time_spent_s,
                "at": a.created_at,
            }
            for a, task_no in attempts.all()
        ],
        "time_spent": sum(s.time_spent_s for s in stats_rows),
    }


async def _recent_exam_primary(session: AsyncSession, user_id: int) -> float | None:
    since = datetime.now(UTC) - timedelta(days=30)
    value = await session.scalar(
        select(Exam.primary_score)
        .where(
            Exam.user_id == user_id,
            Exam.kind == "full",
            Exam.training.is_(False),
            Exam.finished_at >= since,
        )
        .order_by(Exam.finished_at.desc())
        .limit(1)
    )
    return None if value is None else float(value)


async def dashboard(session: AsyncSession, curator: User) -> list[dict[str, Any]]:
    rows = await session.execute(
        select(CuratorLink, User)
        .join(User, User.id == CuratorLink.student_id)
        .where(CuratorLink.curator_id == curator.id, CuratorLink.status == "active")
    )
    now = datetime.now(UTC)
    out = []
    for link, student in rows.all():
        streak = await session.get(Streak, student.id)
        today = study_day(student.tz)
        stats = await session.get(DailyStats, (student.id, today))
        idle = (now - student.last_seen_at).days
        drop = await _confidence_decay(session, student.id, today)
        broken = bool(streak and streak.current == 0 and streak.lost_value > 0)
        card = {
            "student_id": student.id,
            "name": student.first_name,
            "streak": streak.current if streak else 0,
            "threshold_today": bool(stats and stats.threshold_met),
            "rank": (await session.get(Wallet, student.id)).rank,  # type: ignore[union-attr]
        }
        out.append(
            {
                **rules.visible(card, cast(rules.Access, link.access)),
                "link_id": link.id,
                "access": link.access,
                "role": link.role,
                "days_idle": idle,
                "risk": rules.risk_score(idle, drop, broken),
            }
        )
    out.sort(key=lambda r: (-r["risk"], r["name"]))
    return out


async def _confidence_decay(session: AsyncSession, user_id: int, today: date) -> float:
    """Fall of the forecast over the last week, in tenths of a primary point.

    The "falling confidence" signal of the risk sort (9.3), read from the daily
    snapshots the worker writes.
    """
    rows = list(
        await session.scalars(
            select(ConfidenceSnapshot)
            .where(
                ConfidenceSnapshot.user_id == user_id,
                ConfidenceSnapshot.date >= today - timedelta(days=8),
            )
            .order_by(ConfidenceSnapshot.date)
        )
    )
    if len(rows) < 2:
        return 0.0
    return max(0.0, (rows[0].forecast_primary - rows[-1].forecast_primary) * 10)


async def curator_view(session: AsyncSession, curator: User, student_id: int) -> dict[str, Any]:
    link = await link_for_curator(session, curator, student_id)
    student = await session.get(User, student_id)
    assert student is not None
    card = await student_card(session, student)
    visible = rules.visible(card, cast(rules.Access, link.access))
    focus = await _focus(session, link.id, study_day(student.tz))
    return {
        **visible,
        "access": link.access,
        "role": link.role,
        "focus": focus,
        "league_enabled": link.league_enabled,
    }


async def preview(session: AsyncSession, student: User, link_id: int) -> dict[str, Any]:
    """«Так вас видит куратор» (14.3)."""
    link = await link_for_student(session, student, link_id)
    card = await student_card(session, student)
    return rules.visible(card, cast(rules.Access, link.access))


async def nudge(session: AsyncSession, curator: User, student_id: int, code: str) -> dict[str, Any]:
    if code not in rules.NUDGES:
        raise ApiError(422, "bad_nudge", "Выберите одно из готовых сообщений")
    link = await link_for_curator(session, curator, student_id)
    since = datetime.now(UTC) - timedelta(hours=24)
    recent = await session.scalar(
        select(Nudge.id).where(Nudge.link_id == link.id, Nudge.sent_at >= since).limit(1)
    )
    if recent is not None:
        raise ApiError(429, "nudge_limit", "Пинок — не чаще одного в день")
    session.add(Nudge(link_id=link.id, code=code))
    await schedule(
        session,
        student_id,
        "curator_nudge",
        {"text": rules.NUDGES[code]},
        dedupe=f"curator_nudge:{link.id}:{date.today().isoformat()}",
    )
    await session.commit()
    return {"sent": True, "text": rules.NUDGES[code]}


async def _focus(session: AsyncSession, link_id: int, day: date) -> list[int]:
    row = await session.scalar(
        select(CuratorFocus).where(
            CuratorFocus.link_id == link_id, CuratorFocus.week_start == week_start(day)
        )
    )
    return list(row.task_nos) if row else []


async def set_focus(
    session: AsyncSession, curator: User, student_id: int, task_nos: list[int]
) -> dict[str, Any]:
    """Weekly focus topic (9.3): band_weight 1.5 for these tasks in the planner."""
    link = await link_for_curator(session, curator, student_id)
    if link.role != "tutor":
        raise forbidden("Фокус‑тему назначает репетитор")
    tasks = sorted(set(task_nos))
    if not 1 <= len(tasks) <= 3 or any(not 1 <= t <= 27 for t in tasks):
        raise ApiError(422, "bad_focus", "Выберите от одного до трёх заданий 1–27")
    student = await session.get(User, student_id)
    assert student is not None
    week = week_start(study_day(student.tz))
    row = await session.scalar(
        select(CuratorFocus).where(CuratorFocus.link_id == link.id, CuratorFocus.week_start == week)
    )
    if row is None:
        session.add(CuratorFocus(link_id=link.id, task_nos=tasks, week_start=week))
    else:
        row.task_nos = tasks
    await schedule(
        session,
        student_id,
        "curator_focus",
        {"tasks": ", ".join(f"{t}‑е" for t in tasks)},
        dedupe=f"curator_focus:{link.id}:{week.isoformat()}:{'-'.join(map(str, tasks))}",
    )
    await session.commit()
    return {"week_start": week.isoformat(), "task_nos": tasks}


async def update_link(
    session: AsyncSession,
    curator: User,
    student_id: int,
    *,
    league_enabled: bool | None,
    digest_time: Any,
) -> dict[str, Any]:
    link = await link_for_curator(session, curator, student_id)
    if league_enabled is not None:
        if league_enabled and link.role != "tutor":
            # Comparing a child with "other children" is toxic (4.7).
            raise forbidden("Лига доступна только репетиторам")
        link.league_enabled = league_enabled
    if digest_time is not None:
        link.daily_digest_time = digest_time
        # Choosing a digest time is the opt-in to the digest (9.4: optional).
        prefs = await session.get(UserSettings, curator.id)
        if prefs is not None:
            prefs.notifications = {**(prefs.notifications or {}), "cur_digest": True}
    await session.commit()
    return {"league_enabled": link.league_enabled, "daily_digest_time": link.daily_digest_time}


async def league(session: AsyncSession, user: User) -> list[dict[str, Any]]:
    """Weekly XP ranking inside each tutor's group the user belongs to (4.7)."""
    my_links = list(
        await session.scalars(
            select(CuratorLink).where(
                or_(CuratorLink.student_id == user.id, CuratorLink.curator_id == user.id),
                CuratorLink.status == "active",
                CuratorLink.league_enabled.is_(True),
            )
        )
    )
    tutors = sorted({link.curator_id for link in my_links})
    start = week_start(study_day(user.tz))
    out = []
    for tutor_id in tutors:
        members = await session.execute(
            select(User.id, User.first_name, func.coalesce(func.sum(DailyStats.xp), 0))
            .join(CuratorLink, CuratorLink.student_id == User.id)
            .outerjoin(DailyStats, (DailyStats.user_id == User.id) & (DailyStats.date >= start))
            .where(
                CuratorLink.curator_id == tutor_id,
                CuratorLink.status == "active",
                CuratorLink.league_enabled.is_(True),
            )
            .group_by(User.id, User.first_name)
        )
        ranking = sorted(members.all(), key=lambda r: (-int(r[2]), r[0]))
        tutor = await session.get(User, tutor_id)
        out.append(
            {
                "tutor": tutor.first_name if tutor else "",
                "week_start": start.isoformat(),
                "table": [
                    {"place": i + 1, "name": name, "xp": int(xp), "me": uid == user.id}
                    for i, (uid, name, xp) in enumerate(ranking)
                ],
            }
        )
    return out


async def weekly_report(
    session: AsyncSession, curator: User, student_id: int, week: date | None = None
) -> str:
    """A self-contained HTML page (9.3): print it or save it as PDF from the browser."""
    link = await link_for_curator(session, curator, student_id)
    student = await session.get(User, student_id)
    assert student is not None
    start = week_start(week or study_day(student.tz))
    end = start + timedelta(days=6)
    card = rules.visible(await student_card(session, student), cast(rules.Access, link.access))
    days = [
        d for d in card.get("coins_by_day", []) if start.isoformat() <= d["date"] <= end.isoformat()
    ]
    tasks = curriculum().tasks
    esc = html.escape
    rows = "".join(
        f"<tr><td>{esc(d['date'])}</td><td>{d['coins']}</td>"
        f"<td>{'да' if d['coins'] >= d['threshold'] else 'нет'}</td></tr>"
        for d in days
    )
    conf_rows = "".join(
        f"<tr><td>{c['task_no']}</td><td>{esc(tasks[c['task_no']].title)}</td>"
        f"<td>{c['value']:.0f}</td></tr>"
        for c in card.get("confidence", [])
    )
    forecast = card.get("forecast")
    parts = [
        "<!doctype html><html lang=ru><meta charset=utf-8>",
        f"<title>Отчёт: {esc(student.first_name)} — неделя {start:%d.%m}–{end:%d.%m}</title>",
        "<style>body{font:14px system-ui;margin:24px;color:#111}table{border-collapse:collapse}"
        "td,th{border:1px solid #ccc;padding:4px 8px}h2{margin-top:24px}</style>",
        f"<h1>{esc(student.first_name)}: неделя {start:%d.%m.%Y}–{end:%d.%m.%Y}</h1>",
        f"<p>Серия: {card['streak']['current']} (лучшая {card['streak']['best']}). "
        f"Ранг: {esc(str(card.get('rank', '')))}.</p>",
    ]
    if forecast:
        parts.append(
            f"<p>Прогноз: ≈ {forecast['primary']} первичных / {forecast['test']} тестовых "
            f"(±{forecast['margin']}).</p>"
        )
    if rows:
        parts.append(
            "<h2>Монеты по дням</h2><table><tr><th>День</th><th>🪙</th>"
            f"<th>Порог</th></tr>{rows}</table>"
        )
    if conf_rows:
        parts.append(
            "<h2>Уверенность по заданиям</h2><table><tr><th>№</th><th>Тема</th>"
            f"<th>%</th></tr>{conf_rows}</table>"
        )
    parts.append(
        "<p style='color:#666'>Сформировано «Байтом». Уровень доступа: "
        f"{esc(link.access)}.</p></html>"
    )
    return "".join(parts)
