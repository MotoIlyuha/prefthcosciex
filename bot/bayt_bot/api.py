"""The bot talks to the API only through ``/api/internal`` with a shared secret."""

from __future__ import annotations

from typing import Any

import httpx


class ApiClient:
    def __init__(
        self, base_url: str, token: str, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self._base = base_url.rstrip("/")
        self._headers = {"X-Internal-Token": token}
        self._transport = transport

    async def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=15.0, transport=self._transport) as client:
            response = await client.post(self._base + path, json=body, headers=self._headers)
        response.raise_for_status()
        data: dict[str, Any] = response.json()
        return data

    async def start(self, user: dict[str, Any], payload: str) -> dict[str, Any]:
        return await self._post("/internal/bot/start", {"user": user, "payload": payload})

    async def web_link(self, user: dict[str, Any]) -> str:
        return str((await self._post("/internal/bot/web-link", user))["url"])
