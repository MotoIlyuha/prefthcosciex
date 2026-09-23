"""The shop (5.3, 11.8): streak freezes and restores, exam tickets, cosmetics.

Floors and exams are paid where they are used (``floors``, ``exams``); hints and
reveals on the task screen.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.config.loader import economy
from app.core.errors import ApiError, conflict
from app.core.security import random_token
from app.db.models import User, Wallet
from app.logic import streak as streak_logic
from app.logic.timeutil import month_key, study_day
from app.services import events
from app.services import wallet as wallet_service
from app.services.streaks import settle_today, to_state, write
from app.services.users import settings_of


async def catalogue(session: AsyncSession, user: User) -> dict[str, Any]:
    prices = economy().prices
    day = study_day(user.tz)
    streak = await settle_today(session, user.id, day)
    state = to_state(streak)
    settings = await settings_of(session, user.id)
    wallet = await session.get(Wallet, user.id)
    owned = set(settings.cosmetics or [])
    await session.commit()
    return {
        "freeze": {
            "price": prices.freeze,
            "have": streak.freezes,
            "max": economy().streak.max_freezes,
        },
        "restore": {
            "price": streak_logic.restore_price(state, day),
            "lost_value": streak.lost_value,
        },
        "exam_ticket": {
            "price": prices.exam_full,
            "have": wallet.exam_tickets if wallet else 0,
            "max": prices.max_exam_tickets,
        },
        "cosmetics": [
            {**item.model_dump(), "owned": item.id in owned} for item in economy().cosmetics
        ],
    }


async def buy(
    session: AsyncSession, user: User, item: str, idempotency_key: str | None
) -> dict[str, Any]:
    """Buy one item. A replayed ``Idempotency-Key`` never charges twice."""
    prices = economy().prices
    day = study_day(user.tz)
    # The same key replays the same purchase; without one every call is a new one.
    nonce = idempotency_key or random_token(12)
    result: dict[str, Any] = {"item": item}
    if item == "freeze":
        row = await settle_today(session, user.id, day)
        try:
            new_state = streak_logic.buy_freeze(to_state(row))
        except ValueError as exc:
            raise conflict("freeze_limit", "Больше двух заморозок держать нельзя") from exc
        await wallet_service.move(
            session,
            user.id,
            -prices.freeze,
            reason="freeze",
            key=f"freeze:{user.id}:{nonce}",
        )
        write(row, new_state)
        result.update(price=prices.freeze, freezes=row.freezes)
    elif item == "restore":
        row = await settle_today(session, user.id, day)
        state = to_state(row)
        price = streak_logic.restore_price(state, day)
        if price is None:
            raise conflict("cannot_restore", "Серию можно восстановить только в течение 48 часов")
        await wallet_service.move(
            session,
            user.id,
            -price,
            reason="restore",
            key=f"restore:{user.id}:{row.lost_on}",
            meta={"value": row.lost_value},
        )
        write(row, streak_logic.restore(state, day))
        result.update(price=price, streak=row.current)
    elif item == "exam_ticket":
        wallet = await wallet_service.wallet_for_update(session, user.id)
        if wallet.exam_tickets >= prices.max_exam_tickets:
            raise conflict("ticket_limit", f"Не больше {prices.max_exam_tickets} билетов")
        await wallet_service.move(
            session,
            user.id,
            -prices.exam_full,
            reason="exam_ticket",
            key=f"ticket:{user.id}:{nonce}",
        )
        wallet.exam_tickets += 1
        result.update(price=prices.exam_full, tickets=wallet.exam_tickets)
    elif item.startswith("cosmetic:"):
        cosmetic_id = item.removeprefix("cosmetic:")
        cosmetic = next((c for c in economy().cosmetics if c.id == cosmetic_id), None)
        if cosmetic is None:
            raise ApiError(404, "not_found", "Такого товара нет")
        settings = await settings_of(session, user.id)
        if cosmetic_id in (settings.cosmetics or []):
            raise conflict("owned", "Уже куплено")
        await wallet_service.move(
            session,
            user.id,
            -cosmetic.price,
            reason="cosmetic",
            key=f"cosmetic:{user.id}:{cosmetic_id}",
        )
        settings.cosmetics = [*(settings.cosmetics or []), cosmetic_id]
        result.update(price=cosmetic.price)
    else:
        raise ApiError(422, "bad_item", "Неизвестный товар")
    await events.track(
        session,
        "shop_buy",
        user.id,
        {"item": item.split(":")[0], "price": result.get("price", 0), "month": month_key(day)},
    )
    after = await session.get(Wallet, user.id)
    result["balance"] = after.balance if after else 0
    await session.commit()
    return result
