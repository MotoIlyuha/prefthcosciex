"""HTTP front of the runner: ``POST /run`` and ``GET /health``.

Standard library only — the smaller the attack surface next to untrusted code, the
better. Only the API and the worker reach it (internal network), and every call
must carry the shared bearer token.
"""

from __future__ import annotations

import hmac
import json
import os
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from bayt_runner.sandbox import MAX_FILES_BYTES, RejectedError, nsjail_binary, run

MAX_BODY = MAX_FILES_BYTES * 2 + 1024 * 1024
SLOTS = threading.BoundedSemaphore(int(os.environ.get("RUNNER_CONCURRENCY", os.cpu_count() or 2)))


def _token() -> str:
    return os.environ.get("RUNNER_TOKEN", "")


def _allow_unsafe() -> bool:
    return os.environ.get("RUNNER_ALLOW_UNSAFE") == "1"


class Handler(BaseHTTPRequestHandler):
    server_version = "bayt-runner"
    sys_version = ""

    def _send(self, status: int, body: dict[str, object]) -> None:
        payload = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args: object) -> None:
        # Never log request bodies: they hold student code.
        return

    def do_GET(self) -> None:
        if self.path == "/health":
            self._send(200, {"status": "ok", "nsjail": nsjail_binary() is not None})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self) -> None:
        if self.path != "/run":
            self._send(404, {"error": "not found"})
            return
        expected = _token()
        given = self.headers.get("Authorization", "").removeprefix("Bearer ")
        if not expected or not hmac.compare_digest(given, expected):
            self._send(HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})
            return
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > MAX_BODY:
            self._send(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "body too large"})
            return
        try:
            body = json.loads(self.rfile.read(length))
            code = str(body["code"])
            encoding = str(body.get("encoding", "latin-1"))
            files = {
                str(k): str(v).encode(encoding) for k, v in dict(body.get("files", {})).items()
            }
        except (ValueError, KeyError, TypeError, LookupError):
            self._send(HTTPStatus.BAD_REQUEST, {"error": "bad request"})
            return
        if not SLOTS.acquire(timeout=15):
            self._send(HTTPStatus.SERVICE_UNAVAILABLE, {"error": "busy"})
            return
        try:
            result = run(code, files, allow_unsafe=_allow_unsafe())
        except RejectedError as exc:
            self._send(HTTPStatus.UNPROCESSABLE_ENTITY, {"error": str(exc)})
            return
        except RuntimeError as exc:
            self._send(HTTPStatus.SERVICE_UNAVAILABLE, {"error": str(exc)})
            return
        finally:
            SLOTS.release()
        self._send(200, result.as_dict())


def make_server(host: str = "0.0.0.0", port: int = 8081) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), Handler)


def main() -> None:
    if not _token():
        raise SystemExit("RUNNER_TOKEN is required")
    if nsjail_binary() is None and not _allow_unsafe():
        raise SystemExit("nsjail not found; set RUNNER_ALLOW_UNSAFE=1 only for local development")
    server = make_server(port=int(os.environ.get("RUNNER_PORT", "8081")))
    server.serve_forever()


if __name__ == "__main__":
    main()
