"""Client for the sandboxed code runner (``runner/``), the server side of 7.5.2."""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from app.settings import get_settings


@dataclass(frozen=True, slots=True)
class RunResult:
    ok: bool
    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool
    duration_ms: int


class RunnerUnavailableError(RuntimeError):
    """The runner could not be reached; the caller defers the check to the worker."""


async def run(code: str, files: dict[str, bytes], *, timeout_s: float = 12.0) -> RunResult:
    settings = get_settings()
    payload = {
        "code": code,
        "files": {name: data.decode("latin-1") for name, data in files.items()},
        "encoding": "latin-1",
    }
    try:
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            response = await client.post(
                f"{settings.runner_url.rstrip('/')}/run",
                json=payload,
                headers={"Authorization": f"Bearer {settings.runner_token}"},
            )
    except httpx.HTTPError as exc:
        raise RunnerUnavailableError(str(exc)) from exc
    if response.status_code != 200:
        raise RunnerUnavailableError(f"runner returned {response.status_code}")
    data = response.json()
    return RunResult(
        ok=bool(data["ok"]),
        stdout=str(data["stdout"]),
        stderr=str(data["stderr"]),
        exit_code=int(data["exit_code"]),
        timed_out=bool(data["timed_out"]),
        duration_ms=int(data["duration_ms"]),
    )
