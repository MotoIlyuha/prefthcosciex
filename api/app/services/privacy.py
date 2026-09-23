"""Personal data (14.3, 12.7): export on request, full deletion after 7 days."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Base
from app.db.models import (
    Attempt,
    CuratorLink,
    DailyStats,
    DifficultyFeedback,
    Event,
    Exam,
    ExamAnswer,
    Instance,
    IssueReport,
    Notification,
    SkillStateRow,
    Streak,
    Transaction,
    User,
    UserFloor,
    UserSettings,
    Wallet,
)

DELETE_AFTER = timedelta(days=7)


def _plain(row: Base, skip: frozenset[str] = frozenset()) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for column in row.__table__.columns:
        if column.key in skip:
            continue
        value = getattr(row, column.key)
        if isinstance(value, datetime | date | time):
            value = value.isoformat()
        out[column.key] = value
    return out


async def export(session: AsyncSession, user: User) -> dict[str, Any]:
    """Everything stored about the user, as JSON. Hidden seeds and answers of open
    tasks stay out: they are part of the anti-cheat, not personal data."""
    uid = user.id

    async def rows(
        model: type[Base], column: Any, skip: frozenset[str] = frozenset()
    ) -> list[dict[str, Any]]:
        return [_plain(r, skip) for r in await session.scalars(select(model).where(column == uid))]

    instances = [
        _plain(r, frozenset({"hidden_seed", "answer", "answer_hash", "reference_code"}))
        | ({"answer": r.answer} if r.state in ("solved", "failed", "revealed", "expired") else {})
        for r in await session.scalars(select(Instance).where(Instance.user_id == uid))
    ]
    exam_ids = [e["id"] for e in await rows(Exam, Exam.user_id)]
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "user": _plain(user),
        "settings": await rows(UserSettings, UserSettings.user_id),
        "wallet": await rows(Wallet, Wallet.user_id),
        "streak": await rows(Streak, Streak.user_id),
        "floors": await rows(UserFloor, UserFloor.user_id),
        "transactions": await rows(Transaction, Transaction.user_id),
        "daily_stats": await rows(DailyStats, DailyStats.user_id),
        "skills": await rows(SkillStateRow, SkillStateRow.user_id),
        "instances": instances,
        "attempts": await rows(Attempt, Attempt.user_id),
        "difficulty_feedback": await rows(DifficultyFeedback, DifficultyFeedback.user_id),
        "exams": await rows(Exam, Exam.user_id),
        "exam_answers": [
            _plain(r)
            for r in await session.scalars(
                select(ExamAnswer).where(ExamAnswer.exam_id.in_(exam_ids))
            )
        ],
        "curator_links": [
            _plain(r)
            for r in await session.scalars(
                select(CuratorLink).where(
                    (CuratorLink.student_id == uid) | (CuratorLink.curator_id == uid)
                )
            )
        ],
        "notifications": await rows(Notification, Notification.user_id),
        "issue_reports": await rows(IssueReport, IssueReport.user_id),
        "events": await rows(Event, Event.user_id),
    }


async def request_deletion(session: AsyncSession, user: User) -> dict[str, Any]:
    """Deletion completes in 7 days; signing in before that cancels it (14.3)."""
    now = datetime.now(UTC)
    user.delete_requested_at = user.delete_requested_at or now
    from app.services.auth import logout

    await logout(session, user.id)
    return {"delete_at": (user.delete_requested_at + DELETE_AFTER).isoformat()}


async def purge_due(session: AsyncSession, now: datetime | None = None) -> int:
    """Delete accounts whose grace period is over. Cascades remove every row."""
    moment = now or datetime.now(UTC)
    ids = list(
        await session.scalars(
            select(User.id).where(
                User.delete_requested_at.is_not(None),
                User.delete_requested_at < moment - DELETE_AFTER,
            )
        )
    )
    if not ids:
        return 0
    await session.execute(delete(Event).where(Event.user_id.in_(ids)))
    await session.execute(delete(User).where(User.id.in_(ids)))
    await session.commit()
    return len(ids)
