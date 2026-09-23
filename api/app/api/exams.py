"""/exams — exam mode (8)."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.api.common import IdemKey, LimitedUser, idempotent
from app.core.deps import Session
from app.services import exams

router = APIRouter(prefix="/exams", tags=["exams"])


@router.get("")
async def list_exams(user: LimitedUser, session: Session) -> dict[str, Any]:
    return {
        "offer": await exams.offer(session, user),
        "history": await exams.history(session, user),
    }


class ExamIn(BaseModel):
    kind: Literal["full", "half", "block"]
    task_no: int | None = Field(default=None, ge=1, le=27)
    training: bool = False


@router.post("")
async def start(
    body: ExamIn, user: LimitedUser, session: Session, key: IdemKey = None
) -> dict[str, Any]:
    async def act() -> dict[str, Any]:
        exam = await exams.start(
            session,
            user,
            body.kind,
            task_no=body.task_no,
            training=body.training,
            idempotency_key=key,
        )
        return await exams.view(session, user, exam)

    return await idempotent(user.id, key, act)


@router.get("/{exam_id}")
async def get_exam(exam_id: int, user: LimitedUser, session: Session) -> dict[str, Any]:
    exam = await exams.owned(session, user, exam_id)
    return await exams.view(session, user, exam)


class ExamAnswerIn(BaseModel):
    position: int = Field(ge=1, le=27)
    answer: str = Field(max_length=4000)
    time_spent_s: int = Field(default=0, ge=0, le=86400)


@router.post("/{exam_id}/answers")
async def save_answer(
    exam_id: int, body: ExamAnswerIn, user: LimitedUser, session: Session
) -> dict[str, Any]:
    """KEGE-style «Сохранить»: stored without feedback until the finish."""
    exam = await exams.owned(session, user, exam_id)
    return await exams.save_answer(
        session, user, exam, body.position, body.answer, body.time_spent_s
    )


@router.post("/{exam_id}/pause")
async def pause(exam_id: int, user: LimitedUser, session: Session) -> dict[str, Any]:
    exam = await exams.owned(session, user, exam_id)
    return await exams.pause(session, exam, True)


@router.post("/{exam_id}/resume")
async def resume(exam_id: int, user: LimitedUser, session: Session) -> dict[str, Any]:
    exam = await exams.owned(session, user, exam_id)
    return await exams.pause(session, exam, False)


@router.post("/{exam_id}/finish")
async def finish(
    exam_id: int, user: LimitedUser, session: Session, key: IdemKey = None
) -> dict[str, Any]:
    async def act() -> dict[str, Any]:
        exam = await exams.owned(session, user, exam_id)
        return await exams.finish(session, user, exam)

    return await idempotent(user.id, key, act)
