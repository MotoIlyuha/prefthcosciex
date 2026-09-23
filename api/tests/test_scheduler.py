"""Worker jobs (app.services.scheduler): local times, limits, delivery, maintenance."""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime, time, timedelta

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.initdata import TelegramUser
from app.db.models import (
    CuratorLink,
    DailyPlan,
    DailyStats,
    Instance,
    Notification,
    Streak,
    User,
    UserSettings,
)
from app.services import scheduler, telegram
from app.services.users import ensure_user
from tests.conftest import JobRecorder

MONDAY = datetime(2026, 10, 5, tzinfo=UTC)


class BotApi:
    def __init__(self) -> None:
        self.sent: list[dict[str, object]] = []
        self.status = 200

    def handler(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if self.status != 200:
            return httpx.Response(self.status, json={"ok": False, "description": "blocked"})
        self.sent.append(body)
        return httpx.Response(200, json={"ok": True, "result": {}})


@pytest.fixture
def bot_api() -> Iterator[BotApi]:
    api = BotApi()
    telegram.set_transport(httpx.MockTransport(api.handler))
    yield api
    telegram.set_transport(None)


async def _student(
    db: AsyncSession, tg_id: int, tz: str = "Europe/Moscow", seen: datetime = MONDAY
) -> User:
    user, _ = await ensure_user(db, TelegramUser(tg_id, f"U{tg_id}", None, "ru"))
    user.tz = tz
    user.last_seen_at = seen
    settings = await db.get(UserSettings, user.id)
    assert settings is not None
    settings.onboarding_done = True
    await db.commit()
    return user


async def test_morning_plans_follow_each_time_zone(
    db: AsyncSession, jobs_recorder: JobRecorder
) -> None:
    moscow = await _student(db, 9001, "Europe/Moscow")
    vladivostok = await _student(db, 9002, "Asia/Vladivostok")
    # 20:30 UTC: 05:30 in Vladivostok (a new day), 23:30 in Moscow (still Monday).
    moment = MONDAY.replace(hour=20, minute=30)
    assert await scheduler.morning_plans(db, moment) == 2
    plans = {p.user_id: p.date for p in await db.scalars(select(DailyPlan))}
    assert plans[moscow.id].isoformat() == "2026-10-05"
    assert plans[vladivostok.id].isoformat() == "2026-10-06"
    assert await scheduler.morning_plans(db, moment) == 0  # idempotent
    note = await db.scalar(
        select(Notification).where(
            Notification.user_id == vladivostok.id, Notification.kind == "dailies_open"
        )
    )
    assert note is not None
    local = note.scheduled_at.astimezone(__import__("zoneinfo").ZoneInfo("Asia/Vladivostok"))
    assert local.hour == 16  # the default «дейлики открыты» time


async def test_evening_reminder_is_skipped_once_the_threshold_is_met(
    db: AsyncSession, bot_api: BotApi
) -> None:
    user = await _student(db, 9011)
    evening = MONDAY.replace(hour=16)  # 19:00 in Moscow
    assert await scheduler.evening_reminders(db, evening) == 1
    note = await db.scalar(select(Notification).where(Notification.user_id == user.id))
    assert note is not None and note.kind == "threshold_missed"
    stats = DailyStats(
        user_id=user.id,
        date=MONDAY.date(),
        coins_earned=40,
        coins_capped=0,
        tasks_done=3,
        threshold_met=True,
        easy_day=False,
        vacation=False,
        time_spent_s=0,
        xp=0,
        feedback_bonuses=0,
        free_reveals_used=0,
        similar_counts={},
    )
    db.add(stats)
    await db.commit()
    result = await scheduler.deliver_due(db, MONDAY.replace(hour=17, minute=5))
    assert result == {"sent": 0, "skipped": 1, "failed": 0}
    assert bot_api.sent == []


async def test_long_streak_gets_the_last_chance_message(db: AsyncSession, bot_api: BotApi) -> None:
    user = await _student(db, 9021)
    streak = await db.get(Streak, user.id)
    assert streak is not None
    streak.current, streak.best, streak.last_met_date = 5, 5, MONDAY.date() - timedelta(days=1)
    streak.accounted_until = MONDAY.date() - timedelta(days=1)
    await db.commit()
    await scheduler.evening_reminders(db, MONDAY.replace(hour=16))
    note = await db.scalar(select(Notification).where(Notification.user_id == user.id))
    assert note is not None and note.kind == "streak_risk"
    await scheduler.deliver_due(db, MONDAY.replace(hour=19, minute=1))
    assert bot_api.sent and bot_api.sent[0]["chat_id"] == 9021
    assert "Серия 5" in str(bot_api.sent[0]["text"])
    button = bot_api.sent[0]["reply_markup"]["inline_keyboard"][0][0]  # type: ignore[index]
    assert button["url"].startswith("https://t.me/bayt_test_bot/app?startapp=today")


async def test_blocked_bot_marks_failed_and_temporary_errors_retry(
    db: AsyncSession, bot_api: BotApi
) -> None:
    user = await _student(db, 9031)
    from app.services.notify import schedule

    await schedule(db, user.id, "exam_checked", {"primary": 9}, now=MONDAY.replace(hour=9))
    await db.commit()
    bot_api.status = 403
    await scheduler.deliver_due(db, MONDAY.replace(hour=9, minute=1))
    note = await db.scalar(select(Notification).where(Notification.user_id == user.id))
    assert note is not None and note.status == "failed"
    await schedule(
        db, user.id, "floor_unlocked", {"floor": 2, "title": "x"}, now=MONDAY.replace(hour=9)
    )
    await db.commit()
    bot_api.status = 502
    await scheduler.deliver_due(db, MONDAY.replace(hour=9, minute=2))
    db.expire_all()
    retry = await db.scalar(select(Notification).where(Notification.kind == "floor_unlocked"))
    assert retry is not None and retry.status == "scheduled"
    assert retry.scheduled_at > MONDAY.replace(hour=9, minute=2)


async def test_curator_digest_and_idle_alert(db: AsyncSession) -> None:
    student = await _student(db, 9041, seen=MONDAY - timedelta(days=3))
    parent = await _student(db, 9042)
    link = CuratorLink(
        student_id=student.id,
        curator_id=parent.id,
        status="active",
        access="progress",
        role="parent",
        invited_by=student.id,
        daily_digest_time=time(20, 0),
    )
    db.add(link)
    settings = await db.get(UserSettings, parent.id)
    assert settings is not None
    settings.notifications = {**settings.notifications, "cur_digest": True}
    await db.commit()
    planned = await scheduler.curator_updates(db, MONDAY.replace(hour=17, minute=7))
    assert planned == 2
    kinds = sorted(
        n.kind
        for n in await db.scalars(select(Notification).where(Notification.user_id == parent.id))
    )
    assert kinds == ["cur_digest", "cur_idle"]
    assert await scheduler.curator_updates(db, MONDAY.replace(hour=17, minute=7)) == 0


async def test_weekly_summary_on_sunday_evening(db: AsyncSession) -> None:
    user = await _student(db, 9051)
    sunday = MONDAY + timedelta(days=6)
    assert await scheduler.weekly(db, sunday.replace(hour=10)) == 0
    assert await scheduler.weekly(db, sunday.replace(hour=16)) == 1  # 19:00 Moscow
    note = await db.scalar(select(Notification).where(Notification.user_id == user.id))
    assert note is not None and note.kind == "weekly_summary"


async def test_nightly_expires_snapshots_and_purges(db: AsyncSession) -> None:
    user = await _student(db, 9061, seen=datetime.now(UTC))
    await scheduler.morning_plans(db, datetime.now(UTC))
    rows = list(await db.scalars(select(Instance).where(Instance.user_id == user.id)))
    assert rows
    gone = await _student(db, 9062)
    gone.delete_requested_at = datetime.now(UTC) - timedelta(days=8)
    await db.commit()
    result = await scheduler.nightly(db, datetime.now(UTC) + timedelta(days=2))
    assert result["expired"] >= len(rows)
    assert result["purged"] == 1
    assert result["snapshots"] >= 1


async def test_big_file_is_prebuilt(db: AsyncSession) -> None:
    from app.services.instances import create

    user = await _student(db, 9071)
    row = await create(
        db, user_id=user.id, task_no=27, subtype=None, difficulty=3, seed=5, context="practice"
    )
    await db.commit()
    assert await scheduler.build_big_file(db, row.id) is True
    from app.services.assets import store
    from app.services.instances import asset_key

    name = next(a["name"] for a in row.assets if a.get("deferred"))
    data = await store().get(asset_key(row.id, name))
    assert data is not None and data.count(b"\n") > 100_000
