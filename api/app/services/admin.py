"""Admin panel: economy health (5.4), funnel (15.2), generator errors, anomalies (14.2),
live config (prices, FIPI toggles) and a smoke run of every generator."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from egegen.core.fipi import FipiConfig, load_fipi_config, reload_fipi_config, set_fipi_config
from sqlalchemy import ColumnElement, Integer, case, cast, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.config.loader import (
    apply_overrides,
    clear_overrides,
    curriculum,
    economy,
    floors,
)
from app.core.errors import ApiError, not_found
from app.db.models import (
    Attempt,
    AuditLog,
    ConfidenceSnapshot,
    ConfigOverride,
    CuratorLink,
    DailyStats,
    DifficultyFeedback,
    Instance,
    IssueReport,
    Subtype,
    Transaction,
    User,
    UserSettings,
    Wallet,
)
from app.services import wallet as wallet_service
from app.services.answers import min_seconds
from app.services.notify import schedule

SECTIONS = ("economy", "floors", "curriculum", "fipi")
EARN_REASONS = ("task_reward", "feedback_bonus")


async def economy_health(session: AsyncSession, days: int = 30) -> dict[str, Any]:
    since = datetime.now(UTC) - timedelta(days=days)
    earned = (
        await session.scalar(
            select(func.coalesce(func.sum(Transaction.delta), 0)).where(
                Transaction.created_at >= since, Transaction.reason.in_(EARN_REASONS)
            )
        )
        or 0
    )
    spent = -int(
        await session.scalar(
            select(func.coalesce(func.sum(Transaction.delta), 0)).where(
                Transaction.created_at >= since, Transaction.delta < 0
            )
        )
        or 0
    )
    active_since = datetime.now(UTC) - timedelta(days=7)
    avg_balance = await session.scalar(
        select(func.avg(Wallet.balance))
        .join(User, User.id == Wallet.user_id)
        .where(User.last_seen_at >= active_since)
    )
    failed = (
        await session.scalar(
            select(func.count())
            .select_from(Instance)
            .where(
                Instance.created_at >= since,
                Instance.state.in_(("failed", "revealed")),
                Instance.context.in_(("daily", "practice")),
                Instance.void.is_(False),
            )
        )
        or 0
    )
    revealed = (
        await session.scalar(
            select(func.count())
            .select_from(Instance)
            .where(
                Instance.created_at >= since,
                Instance.state == "revealed",
                Instance.context.in_(("daily", "practice")),
                Instance.void.is_(False),
            )
        )
        or 0
    )
    by_reason = await session.execute(
        select(Transaction.reason, func.sum(Transaction.delta), func.count())
        .where(Transaction.created_at >= since)
        .group_by(Transaction.reason)
    )
    health = economy().health
    ratio = spent / earned if earned else None
    reveal_share = revealed / failed if failed else None
    return {
        "days": days,
        "season_id": economy().season_id,
        "earned": int(earned),
        "spent": spent,
        "spent_to_earned": None if ratio is None else round(ratio, 3),
        "spent_to_earned_ok": ratio is None
        or health.spent_to_earned_min <= ratio <= health.spent_to_earned_max,
        "average_balance_active": round(float(avg_balance or 0), 1),
        "average_balance_ok": float(avg_balance or 0) < health.max_average_balance,
        "reveal_after_error": None if reveal_share is None else round(reveal_share, 3),
        "reveal_after_error_ok": reveal_share is None
        or health.reveal_after_error_min <= reveal_share <= health.reveal_after_error_max,
        "by_reason": [{"reason": r, "sum": int(s), "count": int(c)} for r, s, c in by_reason.all()],
        "targets": health.model_dump(),
    }


async def funnel(session: AsyncSession, days: int = 30) -> dict[str, Any]:
    """Section 15.2 metrics for users who signed up in the window."""
    since = datetime.now(UTC) - timedelta(days=days)
    cohort = select(User.id, User.created_at).where(User.created_at >= since).subquery()
    total = await session.scalar(select(func.count()).select_from(cohort)) or 0

    async def share(condition: Any) -> float | None:
        if not total:
            return None
        n = (
            await session.scalar(
                select(func.count())
                .select_from(cohort)
                .join(UserSettings, UserSettings.user_id == cohort.c.id)
                .where(condition)
            )
            or 0
        )
        return round(n / total, 3)

    first_win = (
        await session.scalar(
            select(func.count(func.distinct(Instance.user_id))).where(
                Instance.user_id.in_(select(cohort.c.id)),
                Instance.context == "onboarding",
                Instance.state == "solved",
            )
        )
        or 0
    )

    async def retention(day_n: int) -> float | None:
        eligible = (
            select(cohort.c.id, cohort.c.created_at)
            .where(cohort.c.created_at <= datetime.now(UTC) - timedelta(days=day_n))
            .subquery()
        )
        base = await session.scalar(select(func.count()).select_from(eligible)) or 0
        if not base:
            return None
        back = (
            await session.scalar(
                select(func.count(func.distinct(DailyStats.user_id)))
                .join(eligible, eligible.c.id == DailyStats.user_id)
                .where(
                    DailyStats.tasks_done > 0,
                    DailyStats.date == func.date(eligible.c.created_at) + day_n,
                )
            )
            or 0
        )
        return round(back / base, 3)

    active_days = await session.execute(
        select(func.count(), func.sum(cast(DailyStats.threshold_met, Integer))).where(
            DailyStats.date >= since.date(), DailyStats.tasks_done > 0
        )
    )
    days_n, met = active_days.one()
    asked = (
        await session.scalar(
            select(func.count())
            .select_from(Instance)
            .where(
                Instance.created_at >= since,
                Instance.task_no > 0,
                Instance.state.in_(("solved", "failed", "revealed")),
                (Instance.hints_used > 0) | (Instance.state != "solved"),
            )
        )
        or 0
    )
    answered = (
        await session.scalar(
            select(func.count())
            .select_from(DifficultyFeedback)
            .where(DifficultyFeedback.created_at >= since)
        )
        or 0
    )
    with_curator = (
        await session.scalar(
            select(func.count(func.distinct(CuratorLink.student_id))).where(
                CuratorLink.status == "active"
            )
        )
        or 0
    )
    users_all = await session.scalar(select(func.count()).select_from(User)) or 0
    muted = (
        await session.scalar(
            select(func.count())
            .select_from(UserSettings)
            .where(text("NOT (user_settings.notifications @? '$.* ? (@ == true)')"))
        )
        or 0
    )
    return {
        "days": days,
        "signed_up": int(total),
        "onboarding_done": await share(UserSettings.onboarding_done.is_(True)),
        "first_win": round(first_win / total, 3) if total else None,
        "placement_done": await share(UserSettings.placement_done.is_(True)),
        "retention": {
            "d1": await retention(1),
            "d7": await retention(7),
            "d30": await retention(30),
        },
        "threshold_days_share": round(int(met or 0) / days_n, 3) if days_n else None,
        "feedback_answered_share": round(answered / asked, 3) if asked else None,
        "with_curator_share": round(with_curator / users_all, 3) if users_all else None,
        "notifications_off_share": round(muted / users_all, 3) if users_all else None,
        "north_star": await north_star(session),
    }


async def north_star(session: AsyncSession) -> float | None:
    """Share of active users whose forecast grew by ≥ 3 primary points in 30 days (15.1)."""
    now = datetime.now(UTC)
    active = list(
        await session.scalars(select(User.id).where(User.last_seen_at >= now - timedelta(days=7)))
    )
    if not active:
        return None
    grew = 0
    measured = 0
    for uid in active:
        rows = list(
            await session.execute(
                select(ConfidenceSnapshot.date, ConfidenceSnapshot.forecast_primary)
                .where(
                    ConfidenceSnapshot.user_id == uid,
                    ConfidenceSnapshot.date >= (now - timedelta(days=31)).date(),
                )
                .order_by(ConfidenceSnapshot.date)
            )
        )
        if len(rows) < 2 or (rows[-1][0] - rows[0][0]).days < 25:
            continue
        measured += 1
        grew += rows[-1][1] - rows[0][1] >= 3
    return round(grew / measured, 3) if measured else None


async def generator_errors(session: AsyncSession, days: int = 30) -> list[dict[str, Any]]:
    since = datetime.now(UTC) - timedelta(days=days)
    issued_rows = await session.execute(
        select(Instance.task_no, func.count())
        .where(Instance.created_at >= since)
        .group_by(Instance.task_no)
    )
    issued = {int(t): int(n) for t, n in issued_rows.all()}
    reports = await session.execute(
        select(
            Instance.task_no,
            func.count(),
            func.sum(case((IssueReport.status == "confirmed", 1), else_=0)),
            func.sum(case((IssueReport.status == "open", 1), else_=0)),
        )
        .join(Instance, Instance.id == IssueReport.instance_id)
        .where(IssueReport.created_at >= since)
        .group_by(Instance.task_no)
    )
    by_task = {t: (int(n), int(c or 0), int(o or 0)) for t, n, c, o in reports.all()}
    out = []
    for t in range(0, 28):
        n_issued = int(issued.get(t, 0))
        reported, confirmed, open_n = by_task.get(t, (0, 0, 0))
        if not n_issued and not reported:
            continue
        rate = confirmed / n_issued if n_issued else 0.0
        out.append(
            {
                "task_no": t,
                "issued": n_issued,
                "reported": reported,
                "confirmed": confirmed,
                "open": open_n,
                "confirmed_rate": round(rate, 5),
                "ok": rate < 0.003,
            }
        )
    return out


async def other_reasons(session: AsyncSession) -> list[dict[str, Any]]:
    """Free-text «другое» for the methodist, grouped by subtype (6.4)."""
    rows = await session.execute(
        select(Instance.subtype_id, DifficultyFeedback.free_text, DifficultyFeedback.created_at)
        .join(Instance, Instance.id == DifficultyFeedback.instance_id)
        .where(DifficultyFeedback.reason_code == "other", DifficultyFeedback.free_text.is_not(None))
        .order_by(Instance.subtype_id, DifficultyFeedback.created_at.desc())
        .limit(500)
    )
    grouped: dict[str, list[str]] = {}
    for subtype, body, _ in rows.all():
        grouped.setdefault(subtype, []).append(body)
    return [{"subtype": s, "count": len(v), "texts": v[:20]} for s, v in grouped.items()]


async def anomalies(session: AsyncSession, days: int = 7) -> list[dict[str, Any]]:
    """Instant correct answers concentrated in one curator's group (14.2). A signal
    for a human, never an automatic sanction."""
    since = datetime.now(UTC) - timedelta(days=days)
    rows = await session.execute(
        select(CuratorLink.curator_id, Instance.task_no, Attempt.time_spent_s)
        .join(Attempt, Attempt.user_id == CuratorLink.student_id)
        .join(Instance, Instance.id == Attempt.instance_id)
        .where(
            CuratorLink.status == "active",
            Attempt.created_at >= since,
            Attempt.is_correct.is_(True),
            Instance.task_no > 0,
        )
    )
    stats: dict[int, list[int]] = {}
    for curator_id, task_no, seconds in rows.all():
        bucket = stats.setdefault(int(curator_id), [0, 0])
        bucket[0] += 1
        bucket[1] += seconds < min_seconds(int(task_no))
    out = [
        {"curator_id": cid, "correct": n, "instant": fast, "share": round(fast / n, 3)}
        for cid, (n, fast) in stats.items()
        if n >= 20 and fast / n > 0.3
    ]
    return sorted(out, key=lambda r: -r["share"])


async def load_overrides(session: AsyncSession) -> None:
    """Apply stored overrides at startup; a broken one is skipped, not fatal."""
    clear_overrides()
    reload_fipi_config()
    for row in await session.scalars(select(ConfigOverride)):
        try:
            _apply(row.section, row.patch)
        except ValueError:
            continue


def _apply(section: str, patch: dict[str, Any]) -> None:
    if section == "fipi":
        base = reload_fipi_config().model_dump()
        merged = _merge(base, patch)
        set_fipi_config(FipiConfig.model_validate(merged))
    else:
        apply_overrides(section, patch)


def _merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


async def config_view(session: AsyncSession) -> dict[str, Any]:
    overrides = {
        r.section: {"patch": r.patch, "updated_at": r.updated_at, "updated_by": r.updated_by}
        for r in await session.scalars(select(ConfigOverride))
    }
    return {
        "economy": economy().model_dump(),
        "floors": floors().model_dump(),
        "curriculum": curriculum().model_dump(),
        "fipi": load_fipi_config().model_dump(),
        "overrides": overrides,
    }


async def set_config(
    session: AsyncSession, admin: User, section: str, patch: dict[str, Any] | None
) -> dict[str, Any]:
    """Change prices or FIPI toggles without a deploy. ``None`` removes the override."""
    if section not in SECTIONS:
        raise not_found("раздел конфигурации")
    if patch is not None and section == "economy" and "season_id" not in patch:
        # Prices are fixed within a season (5.6): a price change needs a new season id.
        changes_prices = any(k in patch for k in ("prices", "base_reward", "modifiers", "day"))
        if changes_prices:
            raise ApiError(
                422, "season_required", "Цены меняются только вместе с season_id (раздел 5.6)"
            )
    try:
        if patch is None:
            row = await session.get(ConfigOverride, section)
            if row is not None:
                await session.delete(row)
        else:
            _apply(section, patch)
            row = await session.get(ConfigOverride, section)
            if row is None:
                session.add(ConfigOverride(section=section, patch=patch, updated_by=admin.id))
            else:
                row.patch, row.updated_by, row.updated_at = patch, admin.id, datetime.now(UTC)
    except ValueError as exc:
        raise ApiError(422, "bad_config", f"Конфигурация не прошла проверку: {exc}") from exc
    session.add(
        AuditLog(actor_id=admin.id, action="config_set", target=section, payload={"patch": patch})
    )
    await session.commit()
    await load_overrides(session)
    return await config_view(session)


def _smoke(seeds: int) -> list[dict[str, Any]]:
    from egegen.core.registry import list_generators
    from egegen.testing import check_instance

    out = []
    for gen in list_generators():
        problems: list[str] = []
        checked = 0
        started = datetime.now(UTC)
        for index, subtype in enumerate(sorted(gen.templates.subtypes)):
            difficulties = (1, 3, 5) if index == 0 else (3,)
            for seed in range(1, seeds + 1):
                for difficulty in difficulties:
                    report = check_instance(gen, seed * 7919 + difficulty, difficulty, subtype)
                    checked += 1
                    problems.extend(str(report) for _ in report.failures[:1])
        elapsed = (datetime.now(UTC) - started).total_seconds()
        out.append(
            {
                "task_no": gen.task_no,
                "version": gen.version,
                "checked": checked,
                "ok": not problems,
                "problems": problems[:10],
                "seconds": round(elapsed, 2),
            }
        )
    return out


async def smoke(seeds: int = 1) -> list[dict[str, Any]]:
    """Generate and cross-check every generator: two solvers, format, determinism."""
    return await run_in_threadpool(_smoke, max(1, min(seeds, 10)))


async def find_users(session: AsyncSession, query: str) -> list[dict[str, Any]]:
    q = query.strip().lstrip("@")
    condition: ColumnElement[bool] = func.lower(User.username).like(f"%{q.lower()}%")
    if q.isdigit():
        condition = or_(condition, User.tg_id == int(q), User.id == int(q))
    rows = await session.execute(
        select(User, Wallet.balance)
        .join(Wallet, Wallet.user_id == User.id)
        .where(condition)
        .limit(50)
    )
    return [
        {
            "id": u.id,
            "tg_id": u.tg_id,
            "name": u.first_name,
            "username": u.username,
            "balance": b,
            "is_admin": u.is_admin,
            "created_at": u.created_at,
            "last_seen_at": u.last_seen_at,
        }
        for u, b in rows.all()
    ]


async def grant(
    session: AsyncSession, admin: User, user_id: int, delta: int, reason: str
) -> dict[str, Any]:
    if not reason.strip():
        raise ApiError(422, "reason_required", "Укажите причину")
    if await session.get(User, user_id) is None:
        raise not_found("пользователь")
    tx = await wallet_service.move(
        session,
        user_id,
        delta,
        reason="admin_grant",
        key=f"admin:{admin.id}:{user_id}:{datetime.now(UTC).timestamp()}",
        meta={"reason": reason, "admin": admin.id},
    )
    session.add(
        AuditLog(
            actor_id=admin.id,
            action="grant",
            target=f"user:{user_id}",
            payload={"delta": delta, "reason": reason},
        )
    )
    await session.commit()
    return {"balance": tx.balance_after}


async def set_subtype_beta(
    session: AsyncSession, admin: User, subtype_id: str, beta: bool, days: int = 3
) -> dict[str, Any]:
    """New generators live only in the «Вызов» slot for three days (16.5)."""
    row = await session.get(Subtype, subtype_id)
    if row is None:
        raise not_found("подтип")
    row.beta = beta
    row.beta_until = (datetime.now(UTC) + timedelta(days=days)).date() if beta else None
    session.add(
        AuditLog(
            actor_id=admin.id,
            action="subtype_beta",
            target=subtype_id,
            payload={"beta": beta, "days": days},
        )
    )
    await session.commit()
    return {"id": row.id, "beta": row.beta, "beta_until": row.beta_until}


async def broadcast_demo(session: AsyncSession, admin: User, summary: str) -> int:
    """«Утверждена демоверсия — что изменилось» (10): one message per user, once."""
    ids = list(await session.scalars(select(User.id).where(User.delete_requested_at.is_(None))))
    sent = 0
    for uid in ids:
        row = await schedule(
            session,
            uid,
            "demo_approved",
            {"summary": summary[:500]},
            dedupe=f"demo_approved:{uid}:{load_fipi_config().version}",
        )
        sent += row is not None
    session.add(
        AuditLog(
            actor_id=admin.id,
            action="broadcast_demo",
            target="all",
            payload={"summary": summary, "sent": sent},
        )
    )
    await session.commit()
    return sent


async def audit(session: AsyncSession, limit: int = 200) -> list[dict[str, Any]]:
    rows = await session.scalars(select(AuditLog).order_by(AuditLog.id.desc()).limit(limit))
    return [
        {
            "id": r.id,
            "actor_id": r.actor_id,
            "action": r.action,
            "target": r.target,
            "payload": r.payload,
            "created_at": r.created_at,
        }
        for r in rows
    ]
