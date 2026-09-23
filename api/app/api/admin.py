"""/admin — for accounts with the admin flag only; every change is audited (14.1)."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from app.core.deps import AdminUser, Session
from app.services import admin, tickets

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/economy")
async def economy_health(
    user: AdminUser, session: Session, days: int = Query(default=30, ge=1, le=365)
) -> dict[str, Any]:
    return await admin.economy_health(session, days)


@router.get("/funnel")
async def funnel(
    user: AdminUser, session: Session, days: int = Query(default=30, ge=1, le=365)
) -> dict[str, Any]:
    return await admin.funnel(session, days)


@router.get("/generators")
async def generators(
    user: AdminUser, session: Session, days: int = Query(default=30, ge=1, le=365)
) -> list[dict[str, Any]]:
    return await admin.generator_errors(session, days)


@router.post("/generators/smoke")
async def smoke(
    user: AdminUser, seeds: int = Query(default=1, ge=1, le=10)
) -> list[dict[str, Any]]:
    return await admin.smoke(seeds)


class BetaIn(BaseModel):
    beta: bool
    days: int = Field(default=3, ge=1, le=30)


@router.patch("/subtypes/{subtype_id}")
async def subtype_beta(
    subtype_id: str, body: BetaIn, user: AdminUser, session: Session
) -> dict[str, Any]:
    return await admin.set_subtype_beta(session, user, subtype_id, body.beta, body.days)


@router.get("/anomalies")
async def anomalies(user: AdminUser, session: Session) -> list[dict[str, Any]]:
    return await admin.anomalies(session)


@router.get("/feedback/other")
async def other_reasons(user: AdminUser, session: Session) -> list[dict[str, Any]]:
    return await admin.other_reasons(session)


@router.get("/issues")
async def issues(
    user: AdminUser, session: Session, status: Literal["open", "confirmed", "rejected"] = "open"
) -> list[dict[str, Any]]:
    return await tickets.queue(session, status)


class ResolveIn(BaseModel):
    confirmed: bool
    resolution: str = Field(default="", max_length=2000)


@router.post("/issues/{issue_id}/resolve")
async def resolve(
    issue_id: int, body: ResolveIn, user: AdminUser, session: Session
) -> dict[str, Any]:
    return await tickets.resolve(
        session, user, issue_id, confirmed=body.confirmed, resolution=body.resolution
    )


@router.get("/issues/regressions")
async def regressions(user: AdminUser, session: Session) -> list[dict[str, Any]]:
    return await tickets.regressions(session)


@router.get("/config")
async def config(user: AdminUser, session: Session) -> dict[str, Any]:
    return await admin.config_view(session)


class ConfigIn(BaseModel):
    patch: dict[str, Any] | None


@router.put("/config/{section}")
async def set_config(
    section: str, body: ConfigIn, user: AdminUser, session: Session
) -> dict[str, Any]:
    """Prices, floors, FIPI toggles for 10/13/23/27 — validated, applied without a deploy."""
    return await admin.set_config(session, user, section, body.patch)


@router.get("/users")
async def users(
    user: AdminUser, session: Session, q: str = Query(min_length=1, max_length=64)
) -> list[dict[str, Any]]:
    return await admin.find_users(session, q)


class GrantIn(BaseModel):
    delta: int = Field(ge=-10000, le=10000)
    reason: str = Field(min_length=3, max_length=500)


@router.post("/users/{user_id}/coins")
async def grant(user_id: int, body: GrantIn, user: AdminUser, session: Session) -> dict[str, Any]:
    return await admin.grant(session, user, user_id, body.delta, body.reason)


class DemoIn(BaseModel):
    summary: str = Field(min_length=10, max_length=500)


@router.post("/broadcast/demo")
async def broadcast_demo(body: DemoIn, user: AdminUser, session: Session) -> dict[str, Any]:
    return {"scheduled": await admin.broadcast_demo(session, user, body.summary)}


@router.get("/audit")
async def audit(user: AdminUser, session: Session) -> list[dict[str, Any]]:
    return await admin.audit(session)


@router.post("/runner/smoke")
async def runner_smoke(user: AdminUser) -> dict[str, Any]:
    return await admin.runner_smoke()


@router.post("/notify/test")
async def notify_test(user: AdminUser, session: Session) -> dict[str, Any]:
    return await admin.notify_admin(session, user)
