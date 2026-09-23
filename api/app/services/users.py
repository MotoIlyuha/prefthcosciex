"""Account lifecycle: first login, admin bootstrap, settings."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.initdata import TelegramUser
from app.db.models import Streak, User, UserFloor, UserSettings, Wallet
from app.settings import get_settings

DEFAULT_NOTIFICATIONS = {
    "dailies_open": True,
    "threshold_missed": True,
    "streak_risk": True,
    "floor_unlocked": True,
    "exam_checked": True,
    "weekly_summary": True,
    "curator_nudge": True,
    "curator_focus": True,
    "demo_approved": True,
    "cur_digest": False,
    "cur_milestone": True,
    "cur_floor": True,
    "cur_exam": True,
    "cur_idle": True,
    "cur_weekly": True,
    "cur_revoked": True,
    "cur_invite": True,
}


async def ensure_user(session: AsyncSession, tg: TelegramUser) -> tuple[User, bool]:
    """Find or create the account behind a Telegram identity. Returns (user, created)."""
    user = await session.scalar(select(User).where(User.tg_id == tg.id))
    if user is not None:
        if user.delete_requested_at is not None:
            # Logging back in during the 7-day grace period cancels the deletion.
            user.delete_requested_at = None
        user.first_name = tg.first_name or user.first_name
        user.username = tg.username
        return user, False

    settings = get_settings()
    is_first = (await session.scalar(select(func.count()).select_from(User))) == 0
    admin = tg.id in settings.admin_ids or (not settings.admin_ids and is_first)
    user = User(
        tg_id=tg.id,
        first_name=tg.first_name,
        username=tg.username,
        role_flags=1 if admin else 0,
    )
    session.add(user)
    await session.flush()
    session.add(UserSettings(user_id=user.id, notifications=dict(DEFAULT_NOTIFICATIONS)))
    session.add(Wallet(user_id=user.id))
    session.add(Streak(user_id=user.id))
    session.add(UserFloor(user_id=user.id, floor_id=1, state="unlocked", unlocked_by="default"))
    await session.flush()
    return user, True


async def settings_of(session: AsyncSession, user_id: int) -> UserSettings:
    row = await session.get(UserSettings, user_id)
    if row is None:
        row = UserSettings(user_id=user_id, notifications=dict(DEFAULT_NOTIFICATIONS))
        session.add(row)
        await session.flush()
    return row
