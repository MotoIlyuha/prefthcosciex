"""/internal — called by the bot only, authenticated with a shared secret."""

from __future__ import annotations

import hmac
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, Field

from app.core.deps import Session
from app.core.errors import ApiError
from app.core.initdata import TelegramUser
from app.services import auth, curators
from app.services.users import ensure_user
from app.settings import get_settings

router = APIRouter(prefix="/internal", tags=["internal"], include_in_schema=False)


async def bot_only(x_internal_token: Annotated[str, Header()] = "") -> None:
    if not hmac.compare_digest(x_internal_token, get_settings().internal_token):
        raise ApiError(403, "forbidden", "Недостаточно прав")


class TgUserIn(BaseModel):
    id: int
    first_name: str = Field(default="", max_length=128)
    username: str | None = Field(default=None, max_length=64)
    language_code: str | None = None


class StartIn(BaseModel):
    user: TgUserIn
    payload: str = Field(default="", max_length=128)


def _tg(user: TgUserIn) -> TelegramUser:
    return TelegramUser(user.id, user.first_name, user.username, user.language_code)


@router.post("/bot/start", dependencies=[Depends(bot_only)])
async def start(body: StartIn, session: Session) -> dict[str, Any]:
    """/start in the bot: registers the chat and handles ``cur_`` invites (9.1)."""
    user, created = await ensure_user(session, _tg(body.user))
    await session.commit()
    result: dict[str, Any] = {"user_id": user.id, "created": created}
    if body.payload.startswith("cur_"):
        try:
            result["curator"] = await curators.accept(session, user, body.payload[4:])
        except ApiError as exc:
            result["curator_error"] = exc.detail
    return result


@router.post("/bot/web-link", dependencies=[Depends(bot_only)])
async def web_link(body: TgUserIn, session: Session) -> dict[str, Any]:
    """/web in the bot: a one-time sign-in link to the web version."""
    return {"url": await auth.create_web_link(session, _tg(body))}
