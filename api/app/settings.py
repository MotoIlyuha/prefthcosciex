"""Runtime settings, read from the environment (see ``.env.example``)."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    bayt_env: Literal["local", "test", "stage", "prod"] = "local"
    public_base_url: str = "http://localhost:8080"

    database_url: str = "postgresql+asyncpg://bayt:bayt@localhost:5432/bayt"
    redis_url: str = "redis://localhost:6379/0"

    jwt_secret: str = Field(default="dev-only-secret-change-me-dev-only-secret", min_length=32)
    jwt_access_ttl_min: int = 15
    jwt_refresh_ttl_days: int = 30

    telegram_bot_token: str = ""
    telegram_bot_username: str = ""
    telegram_webhook_secret: str = ""
    #: The design doc (12.3) caps initData age at 10 minutes.
    telegram_initdata_max_age: int = 600

    #: Shared secret between the bot and the API's /internal endpoints.
    internal_token: str = "dev-internal-token"
    #: POST /auth/dev for local e2e runs. Ignored on stage and prod whatever its value.
    dev_login: bool = False

    runner_url: str = "http://runner:8081"
    runner_token: str = "dev-runner-token"

    s3_endpoint: str = ""
    s3_bucket: str = "bayt"
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_region: str = "us-east-1"
    s3_public_url: str = ""

    posthog_key: str = ""
    posthog_host: str = ""

    admin_telegram_ids: str = ""

    rate_limit_answers_per_min: int = 60
    rate_limit_runs_per_hour: int = 20
    rate_limit_default_per_min: int = 240

    @property
    def admin_ids(self) -> set[int]:
        return {int(x) for x in self.admin_telegram_ids.replace(" ", "").split(",") if x}

    @property
    def is_production_like(self) -> bool:
        return self.bayt_env in ("stage", "prod")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
