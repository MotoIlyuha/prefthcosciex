"""/instances — the task screen (11.4) and the path of levels (11.5)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Response
from pydantic import BaseModel, Field

from app.api.common import AnsweringUser, IdemKey, LimitedUser, RunningUser, idempotent
from app.core.deps import Session
from app.logic.skills import REASONS
from app.services import answers, floors, tasks
from app.services import instances as inst_service
from app.services.users import settings_of

router = APIRouter(tags=["tasks"])


@router.get("/instances/{instance_id}")
async def get_instance(instance_id: int, user: LimitedUser, session: Session) -> dict[str, Any]:
    row = await inst_service.owned(session, instance_id, user.id)
    return await tasks.view(session, user, row)


@router.get("/instances/{instance_id}/assets/{name}")
async def get_asset(instance_id: int, name: str, user: LimitedUser, session: Session) -> Response:
    """Task files (``17.txt``, ``9.ods``…); regenerated from the seed if missing."""
    row = await inst_service.owned(session, instance_id, user.id)
    data = await inst_service.read_asset(row, name)
    meta = next(a for a in row.assets if a["name"] == name)
    return Response(
        data,
        media_type=meta.get("mime", "application/octet-stream"),
        headers={
            "Content-Disposition": f'attachment; filename="{name}"',
            "Cache-Control": "private, max-age=86400",
        },
    )


class AnswerIn(BaseModel):
    answer: str = Field(max_length=4000)
    time_spent_s: int = Field(ge=0, le=86400)
    code: str | None = Field(default=None, max_length=20000)
    method_choice: str | None = Field(default=None, max_length=200)


@router.post("/instances/{instance_id}/answer")
async def answer(
    instance_id: int,
    body: AnswerIn,
    user: AnsweringUser,
    session: Session,
    key: IdemKey = None,
) -> dict[str, Any]:
    """The only place where right and wrong are revealed; the answer itself never is."""

    async def act() -> dict[str, Any]:
        row = await inst_service.owned(session, instance_id, user.id)
        return await answers.submit(
            session,
            user,
            row,
            body.answer,
            time_spent_s=body.time_spent_s,
            code=body.code,
            method_choice=body.method_choice,
        )

    return await idempotent(user.id, key, act)


@router.post("/instances/{instance_id}/hint")
async def hint(
    instance_id: int, user: LimitedUser, session: Session, key: IdemKey = None
) -> dict[str, Any]:
    async def act() -> dict[str, Any]:
        row = await inst_service.owned(session, instance_id, user.id)
        return await tasks.hint(session, user, row)

    return await idempotent(user.id, key, act)


@router.post("/instances/{instance_id}/reveal")
async def reveal(
    instance_id: int, user: LimitedUser, session: Session, key: IdemKey = None
) -> dict[str, Any]:
    async def act() -> dict[str, Any]:
        row = await inst_service.owned(session, instance_id, user.id)
        return await tasks.reveal(session, user, row)

    return await idempotent(user.id, key, act)


class FeedbackIn(BaseModel):
    reason: str = Field(pattern="^(" + "|".join(REASONS) + ")$")
    text: str | None = Field(default=None, max_length=1000)


@router.post("/instances/{instance_id}/feedback")
async def feedback(
    instance_id: int, body: FeedbackIn, user: LimitedUser, session: Session, key: IdemKey = None
) -> dict[str, Any]:
    """«Что было сложным?» (6.4)."""

    async def act() -> dict[str, Any]:
        row = await inst_service.owned(session, instance_id, user.id)
        return await tasks.feedback(session, user, row, body.reason, body.text)

    return await idempotent(user.id, key, act)


class RunIn(BaseModel):
    code: str = Field(min_length=1, max_length=20000)


@router.post("/instances/{instance_id}/run")
async def run(instance_id: int, body: RunIn, user: RunningUser, session: Session) -> dict[str, Any]:
    """Run the student's program on the server runner (nsjail, no network, 10 s)."""
    row = await inst_service.owned(session, instance_id, user.id)
    return await tasks.run(session, user, row, body.code)


@router.post("/instances/{instance_id}/ran", status_code=204)
async def ran_in_browser(
    instance_id: int, body: RunIn, user: LimitedUser, session: Session
) -> Response:
    """The browser (Pyodide) ran the program: it counts as "ran at least once" (7.5.2)."""
    row = await inst_service.owned(session, instance_id, user.id)
    await tasks.mark_code_run(session, row, body.code)
    return Response(status_code=204)


class DraftIn(BaseModel):
    answer: str | None = Field(default=None, max_length=4000)
    code: str | None = Field(default=None, max_length=20000)
    notes: str | None = Field(default=None, max_length=20000)


@router.patch("/instances/{instance_id}/draft")
async def draft(
    instance_id: int, body: DraftIn, user: LimitedUser, session: Session
) -> dict[str, Any]:
    row = await inst_service.owned(session, instance_id, user.id)
    saved = await tasks.save_draft(row, body.model_dump(exclude_none=True))
    await session.commit()
    return {"draft": saved}


class SimilarIn(BaseModel):
    instance_id: int | None = None
    task_no: int | None = Field(default=None, ge=1, le=27)
    subtype: str | None = Field(default=None, max_length=64)


@router.post("/instances/similar")
async def similar(
    body: SimilarIn, user: LimitedUser, session: Session, key: IdemKey = None
) -> dict[str, Any]:
    """A fresh instance of the same kind — free and unlimited (5.5)."""

    async def act() -> dict[str, Any]:
        row = await tasks.similar(
            session, user, instance_id=body.instance_id, task_no=body.task_no, subtype=body.subtype
        )
        return inst_service.public(row)

    return await idempotent(user.id, key, act)


@router.get("/path")
async def path(user: LimitedUser, session: Session) -> dict[str, Any]:
    return await floors.path_view(session, user)


@router.post("/path/{floor}/unlock")
async def unlock(
    floor: int, user: LimitedUser, session: Session, key: IdemKey = None
) -> dict[str, Any]:
    return await idempotent(user.id, key, lambda: floors.unlock(session, user, floor))


@router.post("/path/{floor}/extern")
async def extern(
    floor: int, user: LimitedUser, session: Session, key: IdemKey = None
) -> dict[str, Any]:
    """Three tasks at difficulty 4, all three right opens the floor for free (5.5)."""
    return await idempotent(
        user.id, key, lambda: floors.start_trial(session, user, floor, "extern")
    )


@router.post("/path/{floor}/boss")
async def boss(
    floor: int, user: LimitedUser, session: Session, key: IdemKey = None
) -> dict[str, Any]:
    return await idempotent(user.id, key, lambda: floors.start_trial(session, user, floor, "boss"))


@router.get("/path/python")
async def python_track(user: LimitedUser, session: Session) -> dict[str, Any]:
    """«Python‑минимум» progress (Appendix C)."""
    from egegen.pymin import LESSONS

    from app.services.pymin import EXERCISES_PER_LESSON, progress, track_complete

    solved, first_try, lesson = await progress(session, user.id)
    settings = await settings_of(session, user.id)
    return {
        "enabled": settings.python_level == "none",
        "lesson": lesson,
        "lessons": [{"no": no, "title": title} for no, title in sorted(LESSONS.items())],
        "solved": solved,
        "first_try": first_try,
        "per_lesson": EXERCISES_PER_LESSON,
        "complete": settings.python_track_done or track_complete(solved, first_try),
    }
