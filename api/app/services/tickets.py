"""«Сообщить об ошибке» (7.7) and its moderation (5.5).

A confirmed error refunds every coin spent on the instance plus a compensation,
voids the instance in every metric and records the seed for the regression suite.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.loader import economy
from app.core.errors import ApiError, conflict, not_found
from app.db.models import Attempt, AuditLog, Instance, IssueReport, Transaction, User
from app.services import events
from app.services import instances as inst_service
from app.services import wallet as wallet_service


async def report(session: AsyncSession, user: User, instance_id: int, text: str) -> dict[str, Any]:
    row = await inst_service.owned(session, instance_id, user.id)
    text = text.strip()
    if not 5 <= len(text) <= 2000:
        raise ApiError(422, "bad_text", "Опишите ошибку: от 5 до 2000 символов")
    open_one = await session.scalar(
        select(IssueReport.id).where(
            IssueReport.instance_id == row.id,
            IssueReport.user_id == user.id,
            IssueReport.status == "open",
        )
    )
    if open_one is not None:
        raise conflict("already_reported", "Сообщение по этой задаче уже на проверке")
    issue = IssueReport(instance_id=row.id, user_id=user.id, text=text)
    session.add(issue)
    await events.track(session, "issue_report", user.id, {"task_no": row.task_no})
    await session.commit()
    return {"id": issue.id, "status": issue.status, "sla_hours": 24}


async def mine(session: AsyncSession, user: User) -> list[dict[str, Any]]:
    rows = await session.execute(
        select(IssueReport, Instance.task_no)
        .join(Instance, Instance.id == IssueReport.instance_id)
        .where(IssueReport.user_id == user.id)
        .order_by(IssueReport.created_at.desc())
        .limit(50)
    )
    return [
        {
            "id": r.id,
            "task_no": t,
            "status": r.status,
            "resolution": r.resolution,
            "created_at": r.created_at,
            "resolved_at": r.resolved_at,
        }
        for r, t in rows.all()
    ]


async def queue(session: AsyncSession, status: str = "open") -> list[dict[str, Any]]:
    """Moderation view: seed, generator version and the student's answers (7.7)."""
    rows = await session.execute(
        select(IssueReport, Instance)
        .join(Instance, Instance.id == IssueReport.instance_id)
        .where(IssueReport.status == status)
        .order_by(IssueReport.created_at)
        .limit(200)
    )
    out = []
    for issue, inst in rows.all():
        answers = await session.scalars(
            select(Attempt.answer_raw).where(Attempt.instance_id == inst.id).order_by(Attempt.no)
        )
        out.append(
            {
                "id": issue.id,
                "text": issue.text,
                "created_at": issue.created_at,
                "instance_id": inst.id,
                "task_no": inst.task_no,
                "subtype": inst.subtype_id,
                "difficulty": inst.difficulty,
                "seed": inst.seed,
                "gen_version": inst.gen_version,
                "template_id": inst.meta.get("template_id"),
                "statement_md": inst.statement_md,
                "expected": inst.answer,
                "student_answers": list(answers),
            }
        )
    return out


async def resolve(
    session: AsyncSession, admin: User, issue_id: int, *, confirmed: bool, resolution: str
) -> dict[str, Any]:
    issue = await session.get(IssueReport, issue_id, with_for_update=True)
    if issue is None:
        raise not_found("обращение")
    if issue.status != "open":
        raise conflict("resolved", "Обращение уже рассмотрено")
    now = datetime.now(UTC)
    issue.status = "confirmed" if confirmed else "rejected"
    issue.resolution = resolution[:2000]
    issue.resolved_at = now
    refund = 0
    if confirmed:
        inst = await session.get(Instance, issue.instance_id)
        assert inst is not None
        spent = (
            await session.scalar(
                select(func.coalesce(func.sum(Transaction.delta), 0)).where(
                    Transaction.user_id == issue.user_id,
                    Transaction.ref_type == "instance",
                    Transaction.ref_id == str(inst.id),
                    Transaction.delta < 0,
                )
            )
            or 0
        )
        refund = -int(spent) + economy().safety.ticket_compensation
        await wallet_service.move(
            session,
            issue.user_id,
            refund,
            reason="issue_compensation",
            key=f"issue:{issue.id}",
            ref_type="issue",
            ref_id=issue.id,
            meta={"refund": -int(spent), "compensation": economy().safety.ticket_compensation},
        )
        inst.void = True
    session.add(
        AuditLog(
            actor_id=admin.id,
            action="issue_resolve",
            target=f"issue:{issue.id}",
            payload={"confirmed": confirmed, "refund": refund},
        )
    )
    await session.commit()
    return {"id": issue.id, "status": issue.status, "refund": refund}


async def regressions(session: AsyncSession) -> list[dict[str, Any]]:
    """Seeds of confirmed errors, to be added to the generator regression tests (7.7)."""
    rows = await session.execute(
        select(
            Instance.task_no,
            Instance.seed,
            Instance.difficulty,
            Instance.subtype_id,
            Instance.gen_version,
            IssueReport.resolution,
        )
        .join(IssueReport, IssueReport.instance_id == Instance.id)
        .where(IssueReport.status == "confirmed")
        .order_by(Instance.task_no, Instance.seed)
    )
    return [
        {"task_no": t, "seed": s, "difficulty": d, "subtype": st, "version": v, "note": note}
        for t, s, d, st, v, note in rows.all()
    ]
