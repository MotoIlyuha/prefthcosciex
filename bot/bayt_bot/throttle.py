"""Flood protection (12.6): one handled message per user per interval."""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject


class Throttle(BaseMiddleware):
    def __init__(
        self,
        interval_s: float = 0.7,
        clock: Callable[[], float] = time.monotonic,
        max_users: int = 50_000,
    ) -> None:
        self.interval_s = interval_s
        self.clock = clock
        self.max_users = max_users
        self._last: dict[int, float] = {}

    def allow(self, user_id: int) -> bool:
        now = self.clock()
        last = self._last.get(user_id)
        if last is not None and now - last < self.interval_s:
            return False
        if len(self._last) >= self.max_users:
            self._last.clear()  # bounded memory; losing old stamps is harmless
        self._last[user_id] = now
        return True

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if user is not None and not self.allow(user.id):
            return None
        return await handler(event, data)
