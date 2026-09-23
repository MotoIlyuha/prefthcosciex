"""Bot settings from the environment (see the root ``.env.example``)."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Config:
    token: str
    api_url: str
    internal_token: str
    public_base_url: str
    webhook_secret: str
    mode: str
    app_short_name: str
    bot_username: str

    @classmethod
    def from_env(cls) -> Config:
        return cls(
            token=os.environ.get("TELEGRAM_BOT_TOKEN", ""),
            api_url=os.environ.get("BOT_API_URL", "http://api:8000/api"),
            internal_token=os.environ.get("INTERNAL_TOKEN", ""),
            public_base_url=os.environ.get("PUBLIC_BASE_URL", "http://localhost:8080").rstrip("/"),
            webhook_secret=os.environ.get("TELEGRAM_WEBHOOK_SECRET", ""),
            mode=os.environ.get("BOT_MODE", "webhook"),
            app_short_name=os.environ.get("TELEGRAM_APP_SHORT_NAME", "app"),
            bot_username=os.environ.get("TELEGRAM_BOT_USERNAME", ""),
        )
