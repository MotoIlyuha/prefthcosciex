"""Run one Python program with the task's files, under hard limits.

Production runs every program inside nsjail: fresh user, PID, mount, IPC, UTS and
network namespaces (so no network at all), a read-only minimal filesystem, the
task files in a private writable ``/work``, an empty environment, and rlimits on
CPU time, address space, file size, open files and processes. The process is
unprivileged both inside and outside the jail (uid 65534).

Without nsjail (a developer laptop) the runner refuses to start unless
``RUNNER_ALLOW_UNSAFE=1``; then it falls back to a plain subprocess with the same
rlimits, an empty environment and, when ``unshare`` works, no network namespace.
"""

from __future__ import annotations

import logging
import os
import re
import resource
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

WALL_LIMIT_S = 10
MEMORY_MB = 256
MAX_OUTPUT = 64 * 1024
MAX_CODE = 20_000
MAX_FILES_BYTES = 64 * 1024 * 1024
MAX_FILE_WRITE_MB = 16
NOBODY = 65534
FILE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
log = logging.getLogger("bayt.runner")
# Traces of a program trying to leave the sandbox: network, foreign files, processes.
BLOCKED = re.compile(
    r"Network is unreachable|Errno 101|Errno 99|PermissionError|Operation not permitted|"
    r"No such file or directory: '/(etc|home|root|proc|sys)|Resource temporarily unavailable|"
    r"BlockingIOError"
)
SYSTEM_DIRS = ("/usr", "/lib", "/lib64", "/bin", "/etc/alternatives", "/usr/local")


class RejectedError(ValueError):
    """The request itself is invalid (bad file name, oversized input)."""


@dataclass(frozen=True, slots=True)
class Result:
    ok: bool
    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool
    duration_ms: int

    def as_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "exit_code": self.exit_code,
            "timed_out": self.timed_out,
            "duration_ms": self.duration_ms,
        }


def validate(code: str, files: dict[str, bytes]) -> None:
    if not code.strip():
        raise RejectedError("empty program")
    if len(code) > MAX_CODE:
        raise RejectedError("program too long")
    total = 0
    for name, data in files.items():
        # No paths, no dot-files, no traversal: a file name is a plain name.
        if not FILE_NAME.fullmatch(name) or name == "main.py":
            raise RejectedError(f"bad file name {name!r}")
        total += len(data)
    if total > MAX_FILES_BYTES:
        raise RejectedError("files too large")


def python_binary() -> str:
    """The interpreter for student code: the system one, never a private virtualenv."""
    configured = os.environ.get("RUNNER_PYTHON")
    for candidate in (configured, "/usr/local/bin/python3", "/usr/bin/python3"):
        if candidate and Path(candidate).exists():
            return str(Path(candidate).resolve())
    return str(Path(sys.executable).resolve())


def nsjail_binary() -> str | None:
    return os.environ.get("NSJAIL") or shutil.which("nsjail")


def nsjail_command(workdir: Path, python: str) -> list[str]:
    cmd = [
        nsjail_binary() or "nsjail",
        "--mode",
        "o",
        "--really_quiet",
        "--user",
        f"{NOBODY}:{NOBODY}:1",
        "--group",
        f"{NOBODY}:{NOBODY}:1",
        "--hostname",
        "sandbox",
        "--time_limit",
        str(WALL_LIMIT_S + 1),
        "--rlimit_cpu",
        str(WALL_LIMIT_S),
        "--rlimit_as",
        str(MEMORY_MB),
        "--rlimit_fsize",
        str(MAX_FILE_WRITE_MB),
        "--rlimit_nofile",
        "64",
        "--rlimit_nproc",
        "32",
        "--rlimit_stack",
        "64",
        "--disable_proc",
    ]
    mounts = [d for d in SYSTEM_DIRS if Path(d).is_dir()]
    prefix = str(Path(python).parents[1])
    if not any(prefix == d or prefix.startswith(d + "/") for d in mounts):
        mounts.append(prefix)  # an interpreter installed outside /usr (e.g. by uv)
    for directory in mounts:
        cmd += ["--bindmount_ro", directory]
    cmd += [
        "--bindmount",
        f"{workdir}:/work",
        "--tmpfsmount",
        "/tmp",  # noqa: S108 - a fresh tmpfs inside the jail, not the host /tmp
        "--cwd",
        "/work",
        "--",
        python,
        "-I",
        "-X",
        "utf8",
        "main.py",
    ]
    return cmd


def _limits() -> None:  # pragma: no cover - runs in the child process
    resource.setrlimit(resource.RLIMIT_CPU, (WALL_LIMIT_S, WALL_LIMIT_S))
    memory = MEMORY_MB * 1024 * 1024
    resource.setrlimit(resource.RLIMIT_AS, (memory, memory))
    size = MAX_FILE_WRITE_MB * 1024 * 1024
    resource.setrlimit(resource.RLIMIT_FSIZE, (size, size))
    resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
    os.setsid()


def fallback_command(python: str) -> list[str]:
    base = [python, "-I", "-X", "utf8", "main.py"]
    unshare = shutil.which("unshare")
    if unshare and os.geteuid() == 0:
        return [unshare, "--net", "--", *base]
    return base


def _clip(data: bytes) -> str:
    text = data[:MAX_OUTPUT].decode("utf-8", errors="replace")
    if len(data) > MAX_OUTPUT:
        text += "\n… вывод обрезан (больше 64 КБ)"
    return text


def run(code: str, files: dict[str, bytes], *, allow_unsafe: bool = False) -> Result:
    validate(code, files)
    jail = nsjail_binary()
    if jail is None and not allow_unsafe:
        raise RuntimeError("nsjail is not installed and RUNNER_ALLOW_UNSAFE is not set")
    python = python_binary()
    root = Path(os.environ.get("RUNNER_WORKDIR", tempfile.gettempdir()))
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=root) as tmp:
        workdir = Path(tmp)
        for name, data in files.items():
            (workdir / name).write_bytes(data)
        (workdir / "main.py").write_text(code, encoding="utf-8")
        if jail is not None:
            # The jailed user owns nothing else on the host: give it just this dir.
            workdir.chmod(0o777)
            cmd = nsjail_command(workdir, python)
            preexec = None
        else:
            cmd = fallback_command(python)
            preexec = _limits
        started = time.monotonic()
        try:
            proc = subprocess.run(
                cmd,
                cwd=workdir,
                capture_output=True,
                timeout=WALL_LIMIT_S + 2,
                env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"},
                stdin=subprocess.DEVNULL,
                preexec_fn=preexec,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            return Result(
                False,
                _clip(exc.stdout or b""),
                "Превышен лимит времени: 10 с",
                -9,
                True,
                int((time.monotonic() - started) * 1000),
            )
        elapsed = int((time.monotonic() - started) * 1000)
    timed_out = proc.returncode in (-9, 137) and elapsed >= WALL_LIMIT_S * 1000 - 500
    stderr = _clip(proc.stderr)
    blocked = BLOCKED.search(stderr) or BLOCKED.search(_clip(proc.stdout))
    if blocked:
        # Logged without the program text: the code is the student's, the fact is ours.
        log.warning("sandbox blocked an attempt: %s (exit %s)", blocked.group(0), proc.returncode)
    if timed_out:
        stderr = (stderr + "\nПревышен лимит времени: 10 с").strip()
    elif proc.returncode != 0 and "MemoryError" in stderr:
        stderr += "\nПревышен лимит памяти: 256 МБ"
    return Result(
        proc.returncode == 0, _clip(proc.stdout), stderr, proc.returncode, timed_out, elapsed
    )
