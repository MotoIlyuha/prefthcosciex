"""Scheduling and rendering notifications (design doc 9.4 and 10).

The rules are in :mod:`app.logic.notify`. Here a decision becomes a
``notifications`` row with a unique dedupe key, so sending is idempotent; the
worker delivers due rows through the Bot API with a deep link to the screen.
"""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Notification, Streak, User, UserSettings
from app.logic import notify as rules
from app.logic.timeutil import local_now, zone
from app.settings import get_settings

TEXTS: dict[str, str] = {
    "dailies_open": "Дейлики открыты: {tasks}. ~{minutes} мин.",
    "threshold_missed": "До порога дня {left} 🪙. Одна‑две задачи — и серия цела.",
    "streak_risk": "Серия {streak} 🔥 под угрозой: до конца дня нужно {left} 🪙.",
    "floor_unlocked": "Этаж {floor} «{title}» открыт{how}.",
    "exam_checked": "Экзамен проверен: {primary} первичных{test_part}.",
    "weekly_summary": (
        "Итоги недели: {coins} 🪙, {tasks} задач, серия {streak}. План на неделю готов."
    ),
    "curator_nudge": "{text}",
    "curator_focus": "Куратор попросил уделить внимание: {tasks}.",
    "demo_approved": "Утверждена демоверсия ЕГЭ‑2027. Что изменилось: {summary}",
    "cur_digest": "{name}: порог {threshold}, серия {streak}.",
    "cur_milestone": "{name}: серия {streak} дней 🔥",
    "cur_floor": "{name}: открыт этаж {floor} «{title}».",
    "cur_exam": "{name}: экзамен сдан — {primary} первичных{test_part}.",
    "cur_idle": "{name}: 2 дня без активности.",
    "cur_weekly": "Недельный отчёт по ученикам готов.",
    "cur_revoked": "Доступ к ученику закрыт.",
    "cur_invite": "{name} приглашает вас куратором. Откройте ссылку, чтобы подтвердить.",
}
BUTTONS: dict[str, str] = {
    "exam_checked": "Смотреть разбор",
    "weekly_summary": "Открыть прогресс",
    "cur_invite": "Подтвердить",
}


def render(kind: str, payload: dict[str, Any]) -> str:
    template = TEXTS[kind]
    values = dict(payload)
    if "test" in values and values.get("test"):
        values.setdefault("test_part", f" ({values['test']} тестовых)")
    values.setdefault("test_part", "")
    values.setdefault("how", "")
    try:
        return template.format(**values)
    except KeyError:
        # A missing field must not drop a notification: send the fixed part.
        return template.split("{")[0].strip() or "Байт"


def link(kind: str, payload: dict[str, Any]) -> str:
    username = get_settings().telegram_bot_username or "bayt_bot"
    return rules.deep_link(username, kind, str(payload.get("link", "")))


async def _sent_today(session: AsyncSession, user_id: int, tz: str, curator: bool) -> int:
    local = local_now(tz)
    start = datetime.combine(local.date(), time(0), tzinfo=zone(tz)).astimezone(UTC)
    kinds = rules.CURATOR_KINDS if curator else frozenset(rules.KINDS) - rules.CURATOR_KINDS
    count = await session.scalar(
        select(func.count())
        .select_from(Notification)
        .where(
            Notification.user_id == user_id,
            Notification.kind.in_(kinds),
            Notification.status.in_(("scheduled", "sent")),
            Notification.scheduled_at >= start,
            Notification.scheduled_at < start + timedelta(days=1),
        )
    )
    return int(count or 0)


async def schedule(
    session: AsyncSession,
    user_id: int,
    kind: str,
    payload: dict[str, Any] | None = None,
    *,
    dedupe: str | None = None,
    at: time | None = None,
    now: datetime | None = None,
) -> Notification | None:
    """Plan one notification if the rules allow it; ``None`` when they don't."""
    user = await session.get(User, user_id)
    if user is None or user.delete_requested_at is not None:
        return None
    settings = await session.get(UserSettings, user_id)
    prefs = (settings.notifications if settings else {}) or {}
    moment = now or datetime.now(UTC)
    streak = await session.get(Streak, user_id)
    last_ping = await session.scalar(
        select(func.max(Notification.sent_at)).where(Notification.user_id == user_id)
    )
    decision = rules.decide(
        kind,
        now=moment,
        tz=user.tz,
        enabled=bool(prefs.get(kind, kind not in ("cur_digest",))),
        sent_today=await _sent_today(session, user_id, user.tz, kind in rules.CURATOR_KINDS),
        last_seen=user.last_seen_at,
        streak=streak.current if streak else 0,
        last_weekly_ping=last_ping,
        dailies_time=settings.daily_time if settings else None,
        scheduled_time=at,
    )
    if not decision.send or decision.at is None:
        return None
    local_day = local_now(user.tz, decision.at).date().isoformat()
    key = dedupe or f"{kind}:{user_id}:{local_day}"
    stmt = (
        insert(Notification)
        .values(
            user_id=user_id,
            kind=kind,
            payload=payload or {},
            scheduled_at=decision.at,
            status="scheduled",
            dedupe_key=key,
        )
        .on_conflict_do_nothing(index_elements=["dedupe_key"])
        .returning(Notification.id)
    )
    new_id = await session.scalar(stmt)
    if new_id is None:
        return None
    return await session.get(Notification, new_id)


async def due(session: AsyncSession, limit: int = 200) -> list[Notification]:
    """Rows to deliver now, locked so parallel workers never send twice."""
    rows = await session.scalars(
        select(Notification)
        .where(Notification.status == "scheduled", Notification.scheduled_at <= datetime.now(UTC))
        .order_by(Notification.scheduled_at)
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    return list(rows)


async def mark_opened(session: AsyncSession, user_id: int, notification_id: int) -> None:
    row = await session.get(Notification, notification_id)
    if row is not None and row.user_id == user_id and row.opened_at is None:
        row.opened_at = datetime.now(UTC)
