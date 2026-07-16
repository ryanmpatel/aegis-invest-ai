"""Application configuration.

All credentials come from environment variables (or a local .env file).
Secrets are held in ``SecretStr`` so accidental ``repr``/logging never prints them.

LIVE TRADING: ``live_trading_enabled`` exists only so the rest of the code can
assert it is False. There is no supported configuration that enables live
trading; see ``docs/LIVE_TRADING_CHECKLIST.md``.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Application ---
    app_env: Literal["development", "test", "production"] = "development"
    app_secret_key: SecretStr = SecretStr("dev-only-secret-do-not-use-in-production")
    app_base_url: str = "http://localhost:3000"
    backend_host: str = "127.0.0.1"
    backend_port: int = 8000

    # --- Auth (single-user MVP) ---
    auth_username: str = "admin"
    auth_password_hash: SecretStr = SecretStr("")
    session_cookie_name: str = "aegis_session"
    session_cookie_secure: bool = False
    session_ttl_minutes: int = 480

    # --- Database / Redis ---
    database_url: str = "sqlite+aiosqlite:///./aegis.db"
    redis_url: str = "redis://localhost:6379/0"
    allow_local_lock_fallback: bool = True

    # --- Broker ---
    broker_provider: Literal["mock", "alpaca_paper"] = "mock"
    alpaca_paper_api_key: SecretStr = SecretStr("")
    alpaca_paper_api_secret: SecretStr = SecretStr("")

    # --- Market data ---
    market_data_provider: Literal["mock", "alpaca"] = "mock"
    stale_price_max_age_minutes: int = 30

    # --- AI ---
    ai_provider: Literal["mock", "anthropic"] = "mock"
    ai_api_key: SecretStr = SecretStr("")
    ai_model_name: str = "claude-sonnet-5"
    ai_min_confidence: float = 0.6
    ai_max_article_chars: int = 6000

    # --- Safety ---
    live_trading_enabled: bool = False

    # --- Scheduler ---
    scheduler_enabled: bool = False
    rebalance_cron: str = "0 15 * * MON"

    # --- Notifications ---
    notify_console: bool = True
    notify_email_enabled: bool = False
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: SecretStr = SecretStr("")
    notify_email_to: str = ""
    discord_webhook_url: SecretStr = SecretStr("")
    slack_webhook_url: SecretStr = SecretStr("")

    # --- HTTP hardening ---
    cors_origins: str = "http://localhost:3000"
    rate_limit_per_minute: int = 120
    auth_rate_limit_per_minute: int = 10

    @field_validator("live_trading_enabled")
    @classmethod
    def _live_trading_must_stay_disabled(cls, v: bool) -> bool:
        if v:
            raise ValueError(
                "LIVE_TRADING_ENABLED=true is not supported by this build. "
                "Live trading is permanently disabled; see docs/LIVE_TRADING_CHECKLIST.md."
            )
        return v

    @model_validator(mode="after")
    def _validate_environment(self) -> Settings:
        if self.app_env == "production":
            if self.app_secret_key.get_secret_value() in (
                "",
                "dev-only-secret-do-not-use-in-production",
                "change-me-generate-a-long-random-string",
            ):
                raise ValueError("APP_SECRET_KEY must be set to a strong value in production.")
            if not self.auth_password_hash.get_secret_value():
                raise ValueError("AUTH_PASSWORD_HASH must be set in production.")
        if self.broker_provider == "alpaca_paper" and (
            not self.alpaca_paper_api_key.get_secret_value()
            or not self.alpaca_paper_api_secret.get_secret_value()
        ):
            raise ValueError(
                "BROKER_PROVIDER=alpaca_paper requires ALPACA_PAPER_API_KEY and "
                "ALPACA_PAPER_API_SECRET. Refusing to start without paper credentials."
            )
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_test(self) -> bool:
        return self.app_env == "test"


@lru_cache
def get_settings() -> Settings:
    return Settings()
