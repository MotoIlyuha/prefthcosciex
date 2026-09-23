"""Outgoing Bot API calls: notifications are bot messages with a deep link (10)."""

from __future__ import annotations

from typing import Any

import httpx

from app.settings import get_settings

API = "https://api.telegram.org"
_transport: httpx.AsyncBaseTransport | None = None


def set_transport(transport: httpx.AsyncBaseTransport | None) -> None:
    """Tests route Bot API calls to a mock transport."""
    global _transport
    _transport = transport


class TelegramError(RuntimeError):
    def __init__(self, description: str, *, permanent: bool) -> None:
        super().__init__(description)
        self.permanent = permanent
        """The user blocked the bot or deleted the chat: retrying will not help."""


async def send_message(chat_id: int, text: str, button: tuple[str, str] | None = None) -> None:
    token = get_settings().telegram_bot_token
    if not token:
        raise TelegramError("TELEGRAM_BOT_TOKEN is not configured", permanent=False)
    body: dict[str, Any] = {"chat_id": chat_id, "text": text, "disable_web_page_preview": True}
    if button is not None:
        body["reply_markup"] = {"inline_keyboard": [[{"text": button[0], "url": button[1]}]]}
    async with httpx.AsyncClient(timeout=10.0, transport=_transport) as client:
        response = await client.post(f"{API}/bot{token}/sendMessage", json=body)
    if response.status_code == 200:
        return
    try:
        description = str(response.json().get("description", response.status_code))
    except ValueError:
        description = str(response.status_code)
    permanent = response.status_code in (400, 403)
    raise TelegramError(description, permanent=permanent)
