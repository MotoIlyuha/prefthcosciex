"""HTTP contract used by ``api/app/services/runner_client.py``."""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from collections.abc import Iterator

import pytest

from bayt_runner.server import make_server


@pytest.fixture
def base_url(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    monkeypatch.setenv("RUNNER_TOKEN", "t0ken")
    server = make_server("127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def _post(url: str, body: object, token: str | None = "t0ken") -> tuple[int, dict[str, object]]:
    data = json.dumps(body).encode()
    request = urllib.request.Request(url + "/run", data=data, method="POST")
    request.add_header("Content-Type", "application/json")
    if token is not None:
        request.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(request, timeout=30) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def test_health(base_url: str) -> None:
    with urllib.request.urlopen(base_url + "/health", timeout=5) as resp:
        assert json.loads(resp.read())["status"] == "ok"


def test_run_contract(base_url: str) -> None:
    status, body = _post(
        base_url,
        {
            "code": "print(open('a.txt').read().upper())",
            "files": {"a.txt": "héllo".encode().decode("latin-1")},
            "encoding": "latin-1",
        },
    )
    assert status == 200
    assert body["ok"] is True
    assert body["stdout"] == "HÉLLO\n"
    assert set(body) == {"ok", "stdout", "stderr", "exit_code", "timed_out", "duration_ms"}


def test_token_is_required(base_url: str) -> None:
    assert _post(base_url, {"code": "print(1)"}, token=None)[0] == 401
    assert _post(base_url, {"code": "print(1)"}, token="wrong")[0] == 401


def test_bad_requests(base_url: str) -> None:
    assert _post(base_url, {"files": {}})[0] == 400
    assert _post(base_url, {"code": "print(1)", "files": {"../x": ""}})[0] == 422
