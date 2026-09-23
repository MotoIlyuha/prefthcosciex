"""POST /auth/* — sign-in and token rotation (12.3)."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Cookie, Request, Response
from pydantic import BaseModel, Field

from app.core.deps import CurrentUser, Session
from app.core.errors import ApiError
from app.core.initdata import TelegramUser
from app.core.ratelimit import hit
from app.services import auth as service
from app.services.users import ensure_user
from app.settings import get_settings

router = APIRouter(prefix="/auth", tags=["auth"])
REFRESH_COOKIE = "bayt_refresh"


class TelegramIn(BaseModel):
    init_data: str = Field(min_length=10, max_length=8192)


class WidgetIn(BaseModel):
    id: int
    first_name: str = ""
    last_name: str | None = None
    username: str | None = None
    photo_url: str | None = None
    auth_date: int
    hash: str


class WebLinkIn(BaseModel):
    token: str = Field(min_length=10, max_length=128)


class RefreshIn(BaseModel):
    refresh_token: str | None = None


class DevLoginIn(BaseModel):
    tg_id: int
    first_name: str = "Тест"
    username: str | None = None


async def _ip_limit(request: Request) -> None:
    ip = request.client.host if request.client else "unknown"
    await hit("auth", ip, get_settings().rate_limit_auth_per_min, 60)


def _with_cookie(response: Response, result: dict[str, Any]) -> dict[str, Any]:
    """The web version keeps the refresh token in an httpOnly cookie (12.3)."""
    settings = get_settings()
    response.set_cookie(
        REFRESH_COOKIE,
        result["refresh_token"],
        httponly=True,
        secure=settings.is_production_like,
        samesite="strict",
        path="/api/auth",
        max_age=settings.jwt_refresh_ttl_days * 86400,
    )
    return result


@router.post("/telegram")
async def telegram(body: TelegramIn, request: Request, session: Session) -> dict[str, Any]:
    """Mini App sign-in with ``initData``: HMAC-checked, at most 10 minutes old."""
    await _ip_limit(request)
    return await service.telegram(session, body.init_data)


@router.post("/widget")
async def widget(
    body: WidgetIn, request: Request, response: Response, session: Session
) -> dict[str, Any]:
    """Web version sign-in with the Telegram Login Widget."""
    await _ip_limit(request)
    fields = {k: str(v) for k, v in body.model_dump().items() if v is not None}
    return _with_cookie(response, await service.login_widget(session, fields))


@router.post("/web-link")
async def web_link(
    body: WebLinkIn, request: Request, response: Response, session: Session
) -> dict[str, Any]:
    """Exchange the bot's one-time link for a session in the web version."""
    await _ip_limit(request)
    return _with_cookie(response, await service.web_link(session, body.token))


@router.post("/refresh")
async def refresh(
    body: RefreshIn,
    request: Request,
    response: Response,
    session: Session,
    bayt_refresh: Annotated[str | None, Cookie()] = None,
) -> dict[str, Any]:
    await _ip_limit(request)
    token = body.refresh_token or bayt_refresh
    if not token:
        raise ApiError(401, "bad_refresh", "Войдите заново")
    result = await service.refresh(session, token)
    if bayt_refresh and not body.refresh_token:
        _with_cookie(response, result)
    return result


@router.post("/logout", status_code=204)
async def logout(user: CurrentUser, session: Session, response: Response) -> None:
    await service.logout(session, user.id)
    response.delete_cookie(REFRESH_COOKIE, path="/api/auth")


@router.post("/dev", include_in_schema=False)
async def dev_login(body: DevLoginIn, session: Session) -> dict[str, Any]:
    """Local development and end-to-end tests only; absent on stage and production."""
    settings = get_settings()
    if settings.is_production_like or not settings.dev_login:
        raise ApiError(404, "not_found", "Не найдено")
    user, created = await ensure_user(
        session, TelegramUser(body.tg_id, body.first_name, body.username, "ru")
    )
    return await service.session_for(session, user, created)
