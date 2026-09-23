"""Product analytics (design doc 15.3).

Events go to PostHog when it is configured and to the ``events`` table otherwise.
Every event carries band, floor and Python level, and no personal data: the user
is identified only by the internal numeric id.
"""

from __future__ import annotations

from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Event
from app.settings import get_settings

EVENT_NAMES = frozenset(
    {
        "onboarding_step",
        "placement_done",
        "daily_opened",
        "instance_issued",
        "attempt",
        "hint",
        "reveal",
        "feedback_reason",
        "threshold_met",
        "cap_reached",
        "floor_unlocked",
        "extern_result",
        "exam_started",
        "exam_finished",
        "curator_linked",
        "curator_revoked",
        "notification_sent",
        "notification_opened",
        "shop_buy",
        "issue_report",
        "session_end",
    }
)
CLIENT_EVENTS = frozenset({"onboarding_step", "daily_opened", "session_end", "notification_opened"})
FORBIDDEN_PROPS = frozenset({"tg_id", "username", "first_name", "name", "phone", "email"})


async def track(
    session: AsyncSession,
    name: str,
    user_id: int | None,
    props: dict[str, Any] | None = None,
    *,
    context: dict[str, Any] | None = None,
) -> None:
    if name not in EVENT_NAMES:
        raise ValueError(f"unknown event {name!r}")
    clean = {k: v for k, v in (props or {}).items() if k not in FORBIDDEN_PROPS}
    clean.update(context or {})
    settings = get_settings()
    if settings.posthog_key and settings.posthog_host:
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                await client.post(
                    f"{settings.posthog_host.rstrip('/')}/capture/",
                    json={
                        "api_key": settings.posthog_key,
                        "event": name,
                        "distinct_id": str(user_id or "anonymous"),
                        "properties": clean,
                    },
                )
            return
        except httpx.HTTPError:
            pass  # fall through to the local table rather than lose the event
    session.add(Event(user_id=user_id, name=name, props=clean))
