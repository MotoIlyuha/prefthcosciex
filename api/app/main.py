"""FastAPI application. Everything is served under ``/api`` (Caddy forwards it as is)."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from egegen.core.registry import list_generators
from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api import admin, auth, curators, exams, health, internal, student, tasks
from app.config.loader import validate_all
from app.core import ratelimit
from app.db.session import dispose, session_factory
from app.services import jobs
from app.services.admin import load_overrides
from app.settings import get_settings

log = logging.getLogger("bayt.api")

# Importing these registers the close hooks for placement, extern and boss.
from app.services import floors as _floors  # noqa: E402,F401
from app.services import onboarding as _onboarding  # noqa: E402,F401


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    get_settings().check_production()
    validate_all()  # a broken economy.yaml must stop the boot, not surface later
    if len(list_generators()) != 27:
        raise RuntimeError("expected 27 generators")
    try:
        async with session_factory()() as session:
            await load_overrides(session)
    except Exception:  # pragma: no cover - the DB may be migrating; YAML still applies
        log.exception("config overrides not loaded")
    yield
    await jobs.close()
    await ratelimit.close()
    await dispose()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Байт API",
        version="1.0.0",
        description="Бэкенд Telegram Mini App «Байт» для подготовки к ЕГЭ‑2027 по информатике.",
        lifespan=lifespan,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        redoc_url=None,
    )
    for module in (health, auth, student, tasks, exams, curators, admin, internal):
        app.include_router(module.router, prefix="/api")

    @app.middleware("http")
    async def security_headers(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Cache-Control", "no-store")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        fields = [".".join(str(p) for p in e["loc"][1:]) for e in exc.errors()]
        return JSONResponse(
            status_code=422,
            content={
                "detail": {
                    "code": "validation_error",
                    "message": "Проверьте введённые данные",
                    "fields": fields,
                }
            },
        )

    return app


app = create_app()
