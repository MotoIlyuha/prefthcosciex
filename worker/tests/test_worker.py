"""The ARQ wiring: every job is registered and a pending re-check is retried."""

from __future__ import annotations

import pytest
from arq import Retry

from bayt_worker import main


def test_every_cron_job_and_function_is_registered() -> None:
    crons = {job.name.removeprefix("cron:") for job in main.WorkerSettings.cron_jobs}
    assert crons == {
        "morning_plans",
        "deliver_due",
        "evening_reminders",
        "curator_updates",
        "weekly",
        "nightly",
    }
    names = {fn.__name__ for fn in main.WorkerSettings.functions}
    from app.services.jobs import JOBS

    assert names == set(JOBS)


async def test_pending_recheck_is_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    async def pending(fn: object) -> str:
        return "pending"

    monkeypatch.setattr(main, "_with_session", pending)
    with pytest.raises(Retry):
        await main.recheck_code({}, 1)


async def test_finished_recheck_returns_its_status(monkeypatch: pytest.MonkeyPatch) -> None:
    async def done(fn: object) -> str:
        return "ok"

    monkeypatch.setattr(main, "_with_session", done)
    assert await main.recheck_code({}, 1) == "ok"
