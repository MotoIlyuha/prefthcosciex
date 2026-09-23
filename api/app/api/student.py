"""The student's screens (11.2–11.8): me, today, progress, confidence, wallet, shop,
onboarding, placement, theory, reports, client events."""

from __future__ import annotations

from datetime import date, time, timedelta
from typing import Any, Literal

from egegen.core.fipi import load_fipi_config
from fastapi import APIRouter, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.api.common import IdemKey, LimitedUser, idempotent
from app.core.deps import Session
from app.core.errors import ApiError, conflict, not_found
from app.db.models import CuratorLink, DailyStats, Streak, TheoryCard, Transaction, Wallet
from app.logic import streak as streak_logic
from app.logic.notify import KINDS
from app.logic.rewards import rank_for
from app.logic.timeutil import local_now, month_key, study_day, valid_tz, week_start
from app.services import events as event_service
from app.services import instances as inst_service
from app.services import notify as notify_service
from app.services import onboarding, privacy, progress, shop, tickets
from app.services.daily import stats_for, today_view
from app.services.users import settings_of

router = APIRouter(tags=["student"])


@router.get("/me")
async def me(user: LimitedUser, session: Session) -> dict[str, Any]:
    settings = await settings_of(session, user.id)
    wallet = await session.get(Wallet, user.id)
    streak = await session.get(Streak, user.id)
    students = (
        await session.scalar(
            select(func.count())
            .select_from(CuratorLink)
            .where(CuratorLink.curator_id == user.id, CuratorLink.status == "active")
        )
        or 0
    )
    pending = (
        await session.scalar(
            select(func.count())
            .select_from(CuratorLink)
            .where(CuratorLink.student_id == user.id, CuratorLink.status == "pending")
        )
        or 0
    )
    fipi = load_fipi_config()
    rank, next_xp = rank_for(wallet.xp if wallet else 0)
    suggestion = await onboarding.band_suggestion(session, user)
    await session.commit()
    return {
        "id": user.id,
        "first_name": user.first_name,
        "username": user.username,
        "tz": user.tz,
        "is_admin": user.is_admin,
        "is_curator": students > 0,
        "curator_requests": int(pending),
        "settings": {
            "band": settings.band,
            "band_pending": settings.band_pending,
            "python_level": settings.python_level,
            "daily_time": settings.daily_time.isoformat(timespec="minutes"),
            "notifications": settings.notifications,
            "vacation_days": settings.vacation_days,
            "easy_days": settings.easy_days,
            "challenge_enabled": settings.challenge_enabled,
            "run_code_on_server": settings.run_code_on_server,
            "show_timer": settings.show_timer,
            "cosmetics": settings.cosmetics,
            "onboarding_step": settings.onboarding_step,
            "onboarding_done": settings.onboarding_done,
            "placement_done": settings.placement_done,
            "consent": settings.consent_at is not None,
        },
        "wallet": {
            "balance": wallet.balance if wallet else 0,
            "xp": wallet.xp if wallet else 0,
            "rank": rank,
            "next_rank_xp": next_xp,
            "exam_tickets": wallet.exam_tickets if wallet else 0,
        },
        "streak": {
            "current": streak.current if streak else 0,
            "best": streak.best if streak else 0,
            "freezes": streak.freezes if streak else 0,
        },
        "band_suggestion": suggestion,
        "fipi": {
            "version": fipi.version,
            "approved": fipi.approved,
            "banner": None if fipi.approved else fipi.banner_ru,
        },
        "delete_requested_at": user.delete_requested_at,
    }


class SettingsIn(BaseModel):
    band: Literal["A", "B", "C"] | None = None
    python_level: Literal["none", "little", "yes"] | None = None
    daily_time: time | None = None
    tz: str | None = Field(default=None, max_length=64)
    notifications: dict[str, bool] | None = None
    challenge_enabled: bool | None = None
    run_code_on_server: bool | None = None
    show_timer: bool | None = None


@router.patch("/me/settings")
async def update_settings(body: SettingsIn, user: LimitedUser, session: Session) -> dict[str, Any]:
    settings = await settings_of(session, user.id)
    if body.band is not None:
        settings.band, settings.band_pending = body.band, False
    if body.python_level is not None:
        settings.python_level = body.python_level
    if body.daily_time is not None:
        settings.daily_time = body.daily_time
    if body.tz is not None:
        if not valid_tz(body.tz):
            raise ApiError(422, "bad_tz", "Неизвестный часовой пояс")
        user.tz = body.tz
    if body.notifications is not None:
        unknown = set(body.notifications) - set(KINDS)
        if unknown:
            raise ApiError(
                422, "bad_notification", "Неизвестный тип уведомления", kinds=sorted(unknown)
            )
        settings.notifications = {**(settings.notifications or {}), **body.notifications}
    for field in ("challenge_enabled", "run_code_on_server", "show_timer"):
        value = getattr(body, field)
        if value is not None:
            setattr(settings, field, value)
    await session.commit()
    return await me(user, session)


class OnboardingIn(BaseModel):
    step: int | None = Field(default=None, ge=0, le=5)
    band: Literal["A", "B", "C", "unknown"] | None = None
    python_level: Literal["none", "little", "yes"] | None = None
    tz: str | None = Field(default=None, max_length=64)
    daily_time: time | None = None
    notifications_consent: bool | None = None
    privacy_consent: bool | None = None
    done: bool | None = None


@router.patch("/me/onboarding")
async def update_onboarding(
    body: OnboardingIn, user: LimitedUser, session: Session
) -> dict[str, Any]:
    return await onboarding.update(session, user, body.model_dump(exclude_none=True))


@router.post("/onboarding/first-task")
async def first_task(user: LimitedUser, session: Session) -> dict[str, Any]:
    row = await onboarding.first_task(session, user)
    return inst_service.public(row)


@router.post("/placement/start")
async def placement_start(user: LimitedUser, session: Session) -> dict[str, Any]:
    """«Я уже готовился — проверь меня» (6.5): eight adaptive tasks."""
    row = await onboarding.start_placement(session, user)
    return inst_service.public(row)


class VacationIn(BaseModel):
    days: list[date] = Field(min_length=1, max_length=7)


@router.post("/me/vacation")
async def vacation(body: VacationIn, user: LimitedUser, session: Session) -> dict[str, Any]:
    """Up to 7 days a month, booked at least a day ahead; the streak is frozen (4.3)."""
    settings = await settings_of(session, user.id)
    booked = [date.fromisoformat(d) for d in settings.vacation_days or []]
    requested = sorted(set(body.days) - set(booked))
    months = {month_key(d) for d in requested}
    if len(months) > 1:
        raise ApiError(422, "one_month", "Отпуск бронируется в пределах одного месяца")
    month = next(iter(months), month_key(study_day(user.tz)))
    already = sum(1 for d in booked if month_key(d) == month)
    if not streak_logic.vacation_allowed(requested, already, local_now(user.tz)):
        raise conflict("vacation_denied", "Отпуск — до 7 дней в месяц и не позже чем за день")
    settings.vacation_days = sorted({*settings.vacation_days, *(d.isoformat() for d in requested)})
    await session.commit()
    return {"vacation_days": settings.vacation_days}


class EasyDayIn(BaseModel):
    day: date | None = None


@router.post("/me/easy-day")
async def easy_day(body: EasyDayIn, user: LimitedUser, session: Session) -> dict[str, Any]:
    """One «лёгкий день» a week: the threshold drops to 10 (4.3)."""
    settings = await settings_of(session, user.id)
    today = study_day(user.tz)
    day = body.day or today
    if day < today:
        raise ApiError(422, "past_day", "Лёгкий день нельзя назначить задним числом")
    start = week_start(day)
    used = sum(
        1
        for d in settings.easy_days or []
        if start <= date.fromisoformat(d) < start + timedelta(days=7)
    )
    if day.isoformat() in (settings.easy_days or []):
        return {"easy_days": settings.easy_days}
    if not streak_logic.easy_day_allowed(used):
        raise conflict("easy_day_used", "Лёгкий день — один раз в неделю")
    settings.easy_days = sorted({*(settings.easy_days or []), day.isoformat()})
    if day == today:
        stats = await stats_for(session, user.id, today)
        stats.easy_day = True
    await session.commit()
    return {"easy_days": settings.easy_days}


@router.get("/today")
async def today(user: LimitedUser, session: Session) -> dict[str, Any]:
    return await today_view(session, user)


@router.get("/progress")
async def progress_view(
    user: LimitedUser,
    session: Session,
    range: Literal["7d", "30d", "90d", "all"] = Query(default="30d"),
) -> dict[str, Any]:
    return await progress.progress(session, user, range)


@router.get("/confidence")
async def confidence(user: LimitedUser, session: Session) -> dict[str, Any]:
    return await progress.confidence_overview(session, user)


@router.get("/confidence/{task_no}")
async def confidence_task(task_no: int, user: LimitedUser, session: Session) -> dict[str, Any]:
    return await progress.confidence_detail(session, user, task_no)


@router.get("/wallet")
async def wallet(user: LimitedUser, session: Session) -> dict[str, Any]:
    row = await session.get(Wallet, user.id)
    day = study_day(user.tz)
    stats = await session.get(DailyStats, (user.id, day))
    rank, next_xp = rank_for(row.xp if row else 0)
    return {
        "balance": row.balance if row else 0,
        "xp": row.xp if row else 0,
        "rank": rank,
        "next_rank_xp": next_xp,
        "exam_tickets": row.exam_tickets if row else 0,
        "earned_today": stats.coins_earned if stats else 0,
        "capped_today": stats.coins_capped if stats else 0,
    }


@router.get("/wallet/tx")
async def wallet_tx(
    user: LimitedUser,
    session: Session,
    before_id: int | None = None,
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, Any]:
    query = select(Transaction).where(Transaction.user_id == user.id)
    if before_id is not None:
        query = query.where(Transaction.id < before_id)
    rows = list(await session.scalars(query.order_by(Transaction.id.desc()).limit(limit)))
    return {
        "items": [
            {
                "id": t.id,
                "delta": t.delta,
                "reason": t.reason,
                "ref_type": t.ref_type,
                "ref_id": t.ref_id,
                "balance_after": t.balance_after,
                "created_at": t.created_at,
            }
            for t in rows
        ],
        "next_before_id": rows[-1].id if len(rows) == limit else None,
    }


@router.get("/shop")
async def shop_catalogue(user: LimitedUser, session: Session) -> dict[str, Any]:
    return await shop.catalogue(session, user)


class BuyIn(BaseModel):
    item: str = Field(min_length=3, max_length=64)


@router.post("/shop/buy")
async def shop_buy(
    body: BuyIn, user: LimitedUser, session: Session, key: IdemKey = None
) -> dict[str, Any]:
    return await idempotent(user.id, key, lambda: shop.buy(session, user, body.item, key))


class IssueIn(BaseModel):
    instance_id: int
    text: str = Field(min_length=5, max_length=2000)


@router.post("/reports/issue")
async def report_issue(
    body: IssueIn, user: LimitedUser, session: Session, key: IdemKey = None
) -> dict[str, Any]:
    return await idempotent(
        user.id, key, lambda: tickets.report(session, user, body.instance_id, body.text)
    )


@router.get("/reports")
async def my_reports(user: LimitedUser, session: Session) -> list[dict[str, Any]]:
    return await tickets.mine(session, user)


@router.get("/theory/{task_no}")
async def theory(task_no: int, user: LimitedUser, session: Session) -> dict[str, Any]:
    """Method cards: free, always, whatever the balance (5.5)."""
    rows = list(
        await session.scalars(
            select(TheoryCard).where(TheoryCard.task_no == task_no).order_by(TheoryCard.id)
        )
    )
    if not rows:
        raise not_found("карточки метода")
    return {
        "task_no": task_no,
        "cards": [{"id": r.id, "subtype": r.subtype_id, "body_md": r.body_md} for r in rows],
    }


@router.get("/theory/card/{card_id}")
async def theory_card(card_id: str, user: LimitedUser, session: Session) -> dict[str, Any]:
    row = await session.get(TheoryCard, card_id)
    if row is None:
        raise not_found("карточка метода")
    return {"id": row.id, "task_no": row.task_no, "subtype": row.subtype_id, "body_md": row.body_md}


class ClientEventIn(BaseModel):
    name: str = Field(max_length=48)
    props: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


@router.post("/events", status_code=204)
async def client_event(body: ClientEventIn, user: LimitedUser, session: Session) -> Response:
    """Client-side analytics (15.3): only the whitelisted events, no personal data."""
    if body.name not in event_service.CLIENT_EVENTS:
        raise ApiError(422, "bad_event", "Неизвестное событие")
    settings = await settings_of(session, user.id)
    await event_service.track(
        session,
        body.name,
        user.id,
        dict(list(body.props.items())[:20]),
        context={"band": settings.band, "python_level": settings.python_level},
    )
    await session.commit()
    return Response(status_code=204)


@router.post("/notifications/{notification_id}/opened", status_code=204)
async def notification_opened(
    notification_id: int, user: LimitedUser, session: Session
) -> Response:
    await notify_service.mark_opened(session, user.id, notification_id)
    await event_service.track(session, "notification_opened", user.id, {})
    await session.commit()
    return Response(status_code=204)


@router.get("/me/export")
async def export(user: LimitedUser, session: Session) -> dict[str, Any]:
    """All personal data as JSON (12.7, 14.3)."""
    return await privacy.export(session, user)


@router.delete("/me")
async def delete_me(user: LimitedUser, session: Session) -> dict[str, Any]:
    """Full deletion in 7 days; signing in before that cancels it (14.3)."""
    result = await privacy.request_deletion(session, user)
    await session.commit()
    return result
