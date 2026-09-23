"""Curators (9): the student's side under /curators, the curator's under /curator."""

from __future__ import annotations

from datetime import date, time
from typing import Any, Literal

from fastapi import APIRouter, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from app.api.common import IdemKey, LimitedUser, idempotent
from app.core.deps import Session
from app.logic.curator import NUDGES
from app.services import curators

router = APIRouter(tags=["curators"])


@router.get("/curators")
async def my_curators(user: LimitedUser, session: Session) -> list[dict[str, Any]]:
    return await curators.my_curators(session, user)


class InviteIn(BaseModel):
    role: Literal["parent", "tutor"] = "parent"
    username: str | None = Field(default=None, max_length=64)


@router.post("/curators/invite")
async def invite(
    body: InviteIn, user: LimitedUser, session: Session, key: IdemKey = None
) -> dict[str, Any]:
    """A ``t.me/<bot>?start=cur_<token>`` link living 48 hours (9.1)."""
    return await idempotent(
        user.id, key, lambda: curators.create_invite(session, user, body.role, body.username)
    )


class AcceptIn(BaseModel):
    token: str = Field(min_length=8, max_length=64)


@router.post("/curators/accept")
async def accept(body: AcceptIn, user: LimitedUser, session: Session) -> dict[str, Any]:
    return await curators.accept(session, user, body.token.removeprefix("cur_"))


class AccessIn(BaseModel):
    access: Literal["fact", "progress", "full"]


@router.patch("/curators/{link_id}/access")
async def access(
    link_id: int, body: AccessIn, user: LimitedUser, session: Session
) -> dict[str, Any]:
    return await curators.set_access(session, user, link_id, body.access)


@router.get("/curators/{link_id}/preview")
async def preview(link_id: int, user: LimitedUser, session: Session) -> dict[str, Any]:
    """«Так вас видит куратор» (14.3)."""
    return await curators.preview(session, user, link_id)


@router.delete("/curators/{link_id}", status_code=204)
async def revoke(link_id: int, user: LimitedUser, session: Session) -> Response:
    await curators.revoke(session, user, link_id)
    return Response(status_code=204)


@router.get("/curator/students")
async def students(user: LimitedUser, session: Session) -> dict[str, Any]:
    return {"students": await curators.dashboard(session, user), "nudges": NUDGES}


@router.get("/curator/students/{student_id}")
async def student(student_id: int, user: LimitedUser, session: Session) -> dict[str, Any]:
    return await curators.curator_view(session, user, student_id)


class NudgeIn(BaseModel):
    code: str = Field(max_length=16)


@router.post("/curator/students/{student_id}/nudge")
async def nudge(
    student_id: int, body: NudgeIn, user: LimitedUser, session: Session
) -> dict[str, Any]:
    return await curators.nudge(session, user, student_id, body.code)


class FocusIn(BaseModel):
    task_nos: list[int] = Field(min_length=1, max_length=3)


@router.post("/curator/students/{student_id}/focus")
async def focus(
    student_id: int, body: FocusIn, user: LimitedUser, session: Session
) -> dict[str, Any]:
    return await curators.set_focus(session, user, student_id, body.task_nos)


class LinkIn(BaseModel):
    league_enabled: bool | None = None
    daily_digest_time: time | None = None


@router.patch("/curator/students/{student_id}/link")
async def link_settings(
    student_id: int, body: LinkIn, user: LimitedUser, session: Session
) -> dict[str, Any]:
    return await curators.update_link(
        session,
        user,
        student_id,
        league_enabled=body.league_enabled,
        digest_time=body.daily_digest_time,
    )


@router.get("/curator/students/{student_id}/report", response_class=HTMLResponse)
async def report(
    student_id: int, user: LimitedUser, session: Session, week: date | None = None
) -> HTMLResponse:
    """Weekly report as a printable HTML page (9.3)."""
    return HTMLResponse(await curators.weekly_report(session, user, student_id, week))


@router.get("/league")
async def league(user: LimitedUser, session: Session) -> list[dict[str, Any]]:
    return await curators.league(session, user)
