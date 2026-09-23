"""Coins and XP. The server is the only source of truth for balances (5.6).

Every movement is a ``transactions`` row with a reason, a reference to what caused
it and a unique idempotency key: a repeated request finds the existing row and
returns it instead of paying twice.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import insufficient_funds
from app.db.models import Transaction, Wallet
from app.logic.rewards import rank_for


async def wallet_for_update(session: AsyncSession, user_id: int) -> Wallet:
    wallet = await session.scalar(select(Wallet).where(Wallet.user_id == user_id).with_for_update())
    if wallet is None:
        wallet = Wallet(user_id=user_id)
        session.add(wallet)
        await session.flush()
    return wallet


async def existing(session: AsyncSession, key: str) -> Transaction | None:
    row: Transaction | None = await session.scalar(
        select(Transaction).where(Transaction.idempotency_key == key)
    )
    return row


async def move(
    session: AsyncSession,
    user_id: int,
    delta: int,
    *,
    reason: str,
    key: str,
    ref_type: str = "",
    ref_id: str | int = "",
    meta: dict[str, Any] | None = None,
) -> Transaction:
    """Credit (delta > 0) or debit (delta < 0) exactly once per idempotency key."""
    previous = await existing(session, key)
    if previous is not None:
        return previous
    wallet = await wallet_for_update(session, user_id)
    if delta < 0 and wallet.balance + delta < 0:
        raise insufficient_funds(-delta, wallet.balance)
    wallet.balance += delta
    tx = Transaction(
        user_id=user_id,
        delta=delta,
        reason=reason,
        ref_type=ref_type,
        ref_id=str(ref_id),
        idempotency_key=key,
        balance_after=wallet.balance,
        meta=meta or {},
    )
    session.add(tx)
    await session.flush()
    return tx


async def add_xp(session: AsyncSession, user_id: int, amount: int) -> tuple[str, bool]:
    """Add XP and report the rank, and whether this addition crossed into a new one."""
    wallet = await wallet_for_update(session, user_id)
    before, _ = rank_for(wallet.xp)
    wallet.xp += amount
    after, _ = rank_for(wallet.xp)
    wallet.rank = after
    return after, after != before
