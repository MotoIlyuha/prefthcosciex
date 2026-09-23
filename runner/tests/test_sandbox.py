"""The sandbox keeps untrusted code in: time, memory, network, files, environment."""

from __future__ import annotations

import os

import pytest

from bayt_runner import sandbox
from bayt_runner.sandbox import RejectedError, Result

MODES = ["nsjail", "fallback"]


@pytest.fixture(params=MODES)
def mode(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> str:
    """Every property is checked in both modes. CI builds nsjail, so neither is skipped."""
    if request.param == "fallback":
        monkeypatch.setenv("NSJAIL", "")
        monkeypatch.setattr(sandbox, "nsjail_binary", lambda: None)
    else:
        assert sandbox.nsjail_binary(), "nsjail must be installed (see runner/Dockerfile)"
    monkeypatch.setenv("RUNNER_TOKEN", "secret-token-that-must-not-leak")
    return str(request.param)


def _run(code: str, files: dict[str, bytes] | None = None) -> Result:
    return sandbox.run(code, files or {}, allow_unsafe=True)


def test_prints_and_reads_task_files(mode: str) -> None:
    result = _run("print(sum(int(x) for x in open('17.txt')))", {"17.txt": b"1\n2\n3\n"})
    assert result.ok and result.stdout.strip() == "6"


def test_infinite_loop_is_killed(mode: str) -> None:
    result = _run("while True:\n    pass\n")
    assert not result.ok
    assert result.timed_out or result.exit_code != 0
    assert result.duration_ms < 14_000


def test_memory_is_limited(mode: str) -> None:
    result = _run("x = bytearray(600 * 1024 * 1024)\nprint(len(x))")
    assert not result.ok
    assert "MemoryError" in result.stderr


def test_no_network(mode: str) -> None:
    code = (
        "import socket\n"
        "try:\n"
        "    socket.create_connection(('1.1.1.1', 53), timeout=2)\n"
        "    print('OPEN')\n"
        "except OSError:\n"
        "    print('blocked')\n"
    )
    result = _run(code)
    assert result.stdout.strip() == "blocked"


def test_environment_is_empty(mode: str) -> None:
    assert os.environ["RUNNER_TOKEN"]
    result = _run("import os\nprint(sorted(k for k in os.environ if 'TOKEN' in k))")
    assert result.stdout.strip() == "[]"


def test_output_is_clipped(mode: str) -> None:
    result = _run("print('x' * 300000)")
    assert result.ok
    assert len(result.stdout) < 70 * 1024
    assert "обрезан" in result.stdout


def test_traceback_is_returned(mode: str) -> None:
    result = _run("print(1 / 0)")
    assert not result.ok and "ZeroDivisionError" in result.stderr


@pytest.mark.parametrize("name", ["../etc/passwd", "a/b.txt", ".bashrc", "main.py", "", "x" * 80])
def test_bad_file_names_are_rejected(name: str) -> None:
    with pytest.raises(RejectedError):
        sandbox.validate("print(1)", {name: b""})


def test_oversized_program_is_rejected() -> None:
    with pytest.raises(RejectedError):
        sandbox.validate("#" * 30_000, {})


def test_jail_hides_the_host_filesystem(monkeypatch: pytest.MonkeyPatch) -> None:
    code = (
        "import os\n"
        "print(os.getuid())\n"
        "print(os.path.exists('/etc/passwd'), os.path.exists('/home'), os.path.exists('/root'))\n"
    )
    result = _run(code)
    lines = result.stdout.split()
    assert lines[0] == "65534"
    assert lines[1:] == ["False", "False", "False"]


def test_jail_limits_processes() -> None:
    code = (
        "import os\n"
        "n = 0\n"
        "try:\n"
        "    for _ in range(200):\n"
        "        if os.fork() == 0:\n"
        "            import time; time.sleep(3); os._exit(0)\n"
        "        n += 1\n"
        "except OSError:\n"
        "    pass\n"
        "print(n)\n"
    )
    result = _run(code)
    assert int(result.stdout.split()[-1]) < 40


def test_refuses_to_run_unjailed_without_opt_in(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sandbox, "nsjail_binary", lambda: None)
    with pytest.raises(RuntimeError):
        sandbox.run("print(1)", {}, allow_unsafe=False)


def test_blocked_attempts_are_logged(mode: str, caplog: pytest.LogCaptureFixture) -> None:
    code = "import socket\nsocket.create_connection(('1.1.1.1', 53), timeout=2)\n"
    with caplog.at_level("WARNING", logger="bayt.runner"):
        result = _run(code)
    assert not result.ok
    assert any("sandbox blocked" in r.getMessage() for r in caplog.records)
    assert "socket" not in " ".join(r.getMessage() for r in caplog.records)
