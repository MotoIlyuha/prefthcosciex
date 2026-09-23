"""The user's "day" (design doc 4.2): it starts at 05:00 in the user's own time zone."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.config.loader import economy

DEFAULT_TZ = "Europe/Moscow"


def zone(name: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(name or DEFAULT_TZ)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo(DEFAULT_TZ)


def local_now(tz: str | None, now: datetime | None = None) -> datetime:
    moment = now or datetime.now(UTC)
    return moment.astimezone(zone(tz))


def study_day(tz: str | None, now: datetime | None = None) -> date:
    """The study day a moment belongs to: before 05:00 it is still "yesterday"."""
    local = local_now(tz, now)
    boundary = economy().day.day_starts_at_hour
    if local.hour < boundary:
        return (local - timedelta(days=1)).date()
    return local.date()


def day_bounds(tz: str | None, day: date) -> tuple[datetime, datetime]:
    """UTC instants at which a study day starts and ends (05:00 to 05:00 local)."""
    boundary = economy().day.day_starts_at_hour
    start_local = datetime.combine(day, time(boundary), tzinfo=zone(tz))
    end_local = start_local + timedelta(days=1)
    return start_local.astimezone(UTC), end_local.astimezone(UTC)


def month_key(day: date) -> str:
    return f"{day.year:04d}-{day.month:02d}"


def week_start(day: date) -> date:
    return day - timedelta(days=day.weekday())
