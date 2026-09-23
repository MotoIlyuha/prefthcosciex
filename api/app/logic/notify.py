"""Notification rules (design doc 10): at most two a day, quiet hours, time zones,
per-kind opt-out, throttling for users who stopped coming."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta

from app.logic.timeutil import zone

KINDS: dict[str, dict[str, object]] = {
    # kind: scheduled local time (None = sent on the event) and the deep-link screen
    "dailies_open": {"at": None, "screen": "today"},
    "threshold_missed": {"at": time(20, 0), "screen": "today"},
    "streak_risk": {"at": time(22, 0), "screen": "today"},
    "floor_unlocked": {"at": None, "screen": "path"},
    "exam_checked": {"at": None, "screen": "exam"},
    "weekly_summary": {"at": time(19, 0), "screen": "progress"},
    "curator_nudge": {"at": None, "screen": "today"},
    "curator_focus": {"at": None, "screen": "confidence"},
    "demo_approved": {"at": None, "screen": "profile"},
}
MAX_PER_DAY = 2
QUIET_START = time(23, 0)
QUIET_END = time(8, 0)
STREAK_RISK_MIN = 3
DEFAULT_DAILIES_TIME = time(16, 0)


@dataclass(frozen=True, slots=True)
class Decision:
    send: bool
    at: datetime | None = None
    reason: str = ""


def in_quiet_hours(local: datetime) -> bool:
    t = local.time()
    return t >= QUIET_START or t < QUIET_END


def next_allowed(local: datetime) -> datetime:
    """The first moment outside quiet hours at or after ``local``."""
    if not in_quiet_hours(local):
        return local
    day = local.date() if local.time() < QUIET_END else local.date() + timedelta(days=1)
    return datetime.combine(day, QUIET_END, tzinfo=local.tzinfo)


def decide(
    kind: str,
    *,
    now: datetime,
    tz: str | None,
    enabled: bool,
    sent_today: int,
    last_seen: datetime | None,
    streak: int = 0,
    last_weekly_ping: datetime | None = None,
    dailies_time: time | None = None,
) -> Decision:
    """Whether and when to send one notification. Pure: the caller records the result."""
    if kind not in KINDS:
        raise ValueError(f"unknown notification kind {kind!r}")
    if not enabled:
        return Decision(False, reason="disabled by user")
    if kind == "streak_risk" and streak < STREAK_RISK_MIN:
        return Decision(False, reason="streak shorter than 3 days")

    local = now.astimezone(zone(tz))
    if last_seen is not None:
        idle = now - last_seen
        if idle >= timedelta(days=30) and kind != "demo_approved":
            return Decision(False, reason="inactive for 30 days")
        if idle >= timedelta(days=14):
            if last_weekly_ping is not None and now - last_weekly_ping < timedelta(days=7):
                return Decision(False, reason="inactive: one a week at most")
    if sent_today >= MAX_PER_DAY:
        return Decision(False, reason="daily limit reached")

    scheduled = KINDS[kind]["at"]
    if kind == "dailies_open":
        scheduled = dailies_time or DEFAULT_DAILIES_TIME
    if isinstance(scheduled, time):
        target = datetime.combine(local.date(), scheduled, tzinfo=local.tzinfo)
        if target < local:
            target = local
        when = next_allowed(target)
    else:
        when = next_allowed(local)
    return Decision(True, at=when.astimezone(UTC))


def deep_link(bot_username: str, kind: str, payload: str = "") -> str:
    screen = str(KINDS[kind]["screen"])
    start = f"{screen}_{payload}" if payload else screen
    return f"https://t.me/{bot_username}/app?startapp={start}"
