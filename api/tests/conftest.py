"""Shared fixtures. Tests that need the database use ``client`` / ``db``.

The schema is built by running the real Alembic migrations against the
``bayt_test`` database, then seeded exactly as production is. Every test starts
from empty user tables and an empty Redis database.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import tempfile
import time
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://bayt:bayt@localhost:5432/bayt_test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
os.environ.setdefault("TELEGRAM_BOT_TOKEN", "123456:TEST-TOKEN-for-bayt-tests")
os.environ.setdefault("TELEGRAM_BOT_USERNAME", "bayt_test_bot")
os.environ["BAYT_ENV"] = "test"
os.environ.setdefault("INTERNAL_TOKEN", "test-internal-token")

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import ratelimit
from app.core.initdata import sign_init_data
from app.db.session import session_factory
from app.services import jobs
from app.services.assets import LocalStore, set_store
from app.services.runner_client import RunResult
from app.settings import get_settings

API_DIR = Path(__file__).resolve().parents[1]
BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]


@pytest.fixture(scope="session")
def schema() -> None:
    """Fresh schema via the real migrations, then the production seed."""
    import asyncpg

    url = get_settings().database_url.replace("postgresql+asyncpg", "postgresql")

    async def reset() -> None:
        conn = await asyncpg.connect(url)
        await conn.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
        await conn.close()

    asyncio.run(reset())
    env = {**os.environ, "DATABASE_URL": get_settings().database_url}
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=API_DIR,
        env=env,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [sys.executable, "-m", "app.seed"], cwd=API_DIR, env=env, check=True, capture_output=True
    )


class JobRecorder:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...]]] = []

    async def __call__(self, name: str, args: tuple[Any, ...]) -> None:
        self.calls.append((name, args))


def _run_python(code: str, files: dict[str, bytes], timeout_s: float = 12.0) -> RunResult:
    """Stand-in for the nsjail runner: same contract, a plain subprocess."""
    with tempfile.TemporaryDirectory() as tmp:
        for name, data in files.items():
            Path(tmp, name).write_bytes(data)
        Path(tmp, "main.py").write_text(code, encoding="utf-8")
        started = time.monotonic()
        try:
            proc = subprocess.run(
                [sys.executable, "main.py"],
                cwd=tmp,
                capture_output=True,
                text=True,
                timeout=timeout_s,
            )
        except subprocess.TimeoutExpired:
            return RunResult(False, "", "timeout", -1, True, int(timeout_s * 1000))
        return RunResult(
            proc.returncode == 0,
            proc.stdout,
            proc.stderr,
            proc.returncode,
            False,
            int((time.monotonic() - started) * 1000),
        )


@pytest.fixture
def jobs_recorder() -> Iterator[JobRecorder]:
    recorder = JobRecorder()
    jobs.set_enqueuer(recorder)
    yield recorder
    jobs.set_enqueuer(None)


@pytest.fixture
async def db(
    schema: None, monkeypatch: pytest.MonkeyPatch, jobs_recorder: JobRecorder, tmp_path: Path
) -> AsyncIterator[AsyncSession]:
    async with session_factory()() as session:
        await session.execute(
            text("TRUNCATE users, events, audit_log, config_overrides RESTART IDENTITY CASCADE")
        )
        await session.commit()
    await ratelimit.redis().flushdb()
    set_store(LocalStore(tmp_path / "assets"))

    async def fake_run(code: str, files: dict[str, bytes], *, timeout_s: float = 12.0) -> RunResult:
        return await asyncio.to_thread(_run_python, code, files, timeout_s)

    from app.services import answers, tasks

    monkeypatch.setattr(answers, "run_code", fake_run)
    monkeypatch.setattr(tasks, "run_code", fake_run)
    from egegen.core.fipi import reload_fipi_config

    from app.config.loader import clear_overrides

    clear_overrides()
    reload_fipi_config()
    async with session_factory()() as session:
        yield session
    set_store(None)
    clear_overrides()
    reload_fipi_config()


@pytest.fixture
async def client(db: AsyncSession) -> AsyncIterator[httpx.AsyncClient]:
    from app.main import app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test/api") as c:
        yield c


def init_data(
    tg_id: int,
    first_name: str = "Аня",
    *,
    auth_date: int | None = None,
    username: str | None = None,
    start_param: str | None = None,
) -> str:
    from urllib.parse import urlencode

    fields = {
        "auth_date": str(auth_date or int(time.time())),
        "query_id": "AAHtest",
        "user": json.dumps(
            {"id": tg_id, "first_name": first_name, "username": username, "language_code": "ru"},
            ensure_ascii=False,
        ),
    }
    if start_param:
        fields["start_param"] = start_param
    fields["hash"] = sign_init_data(fields, BOT_TOKEN)
    return urlencode(fields)


async def login(
    client: httpx.AsyncClient, tg_id: int, first_name: str = "Аня", username: str | None = None
) -> dict[str, str]:
    resp = await client.post(
        "/auth/telegram", json={"init_data": init_data(tg_id, first_name, username=username)}
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}
