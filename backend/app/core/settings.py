"""Project-wide settings, parsed from environment variables.

D-15 — fail fast on missing required keys.
D-17 — this is the ONLY module in the backend that may read environment
       variables. Every other module imports `settings` from here.

Required env vars (validated at import time):
    DATABASE_URL, JWT_SECRET_KEY (>=32 chars), JWT_ALGORITHM (HS256),
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES (default 60).

Optional env vars (None when absent):
    OPENAI_API_KEY, GROQ_API_KEY, DISCORD_WEBHOOK_URL, LANGSMITH_API_KEY,
    AMADEUS_API_KEY, AMADEUS_API_SECRET, OPENWEATHER_API_KEY,
    OPEN_EXCHANGE_RATES_APP_ID.
"""
from __future__ import annotations

from typing import Literal

from pydantic import HttpUrl, PostgresDsn, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Validated project settings. Instantiated once as the module-level `settings`."""

    # --- Required ---
    database_url: PostgresDsn
    jwt_secret_key: SecretStr
    jwt_algorithm: Literal["HS256"] = "HS256"
    jwt_access_token_expire_minutes: int = 60

    # --- Optional ---
    openai_api_key: SecretStr | None = None
    groq_api_key: SecretStr | None = None
    discord_webhook_url: HttpUrl | None = None
    langsmith_api_key: SecretStr | None = None
    amadeus_api_key: SecretStr | None = None
    amadeus_api_secret: SecretStr | None = None
    openweather_api_key: SecretStr | None = None
    open_exchange_rates_app_id: SecretStr | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @field_validator("jwt_secret_key")
    @classmethod
    def _jwt_secret_min_length(cls, v: SecretStr) -> SecretStr:
        """D-15: JWT_SECRET_KEY must be at least 32 characters."""
        if len(v.get_secret_value()) < 32:
            raise ValueError("JWT_SECRET_KEY must be at least 32 characters long")
        return v


# Module-level singleton — every other module does `from app.core.settings import settings`.
settings = Settings()
