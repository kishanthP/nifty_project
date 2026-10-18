"""All configuration comes from environment variables (or the .env file).

Every setting has a safe default for local development, so the app starts even
before you fill in Angel One or Firebase details.
"""

from functools import lru_cache
from typing import Literal

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ProviderName = Literal["mock", "yahoo", "angelone"]


class Settings(BaseSettings):
    # Looks for .env in the current folder, then one level up (the project root).
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    # --- General ---
    environment: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"
    frontend_url: str = "http://localhost:5174"
    cors_origins: str = "http://localhost:5174"

    # --- Storage ---
    database_url: str = "postgresql+asyncpg://share_market:share_market@localhost:5432/share_market"
    test_database_url: str | None = None
    # Hosted databases have small connection limits (Supabase free: about 15).
    db_pool_size: int = 10
    db_max_overflow: int = 20
    redis_url: str = "redis://localhost:6379/0"
    test_redis_url: str | None = None
    # Run the market worker inside the API process, for hosts without background
    # workers (Render's free plan). Normally the worker is a separate service.
    run_worker_in_api: bool = False

    # --- Market data ---
    market_data_provider: ProviderName = "mock"
    fallback_provider: ProviderName | None = None
    fallback_after_seconds: int = 60

    angelone_api_key: str = ""
    angelone_client_code: str = ""
    angelone_pin: SecretStr = SecretStr("")
    angelone_totp_secret: SecretStr = SecretStr("")
    # Angel One sessions expire daily; the worker logs in again after this IST time.
    angelone_relogin_time: str = "08:30"

    yahoo_poll_seconds: float = 5.0

    mock_start_price: float = 22550.0
    mock_volatility: float = 3.0
    mock_tick_seconds: float = 1.0

    # --- Firebase ---
    firebase_credentials_file: str | None = None
    # Alternative for hosts without secret files: the service-account JSON itself
    # (or base64 of it). Used instead of the file when set.
    firebase_credentials_json: SecretStr = SecretStr("")
    auth_dev_mode: bool = False

    # --- Alerts / realtime tuning ---
    max_active_alerts_per_user: int = 50
    max_devices_per_user: int = 10
    alert_eval_interval_seconds: float = 1.0
    quote_publish_interval_seconds: float = 0.5
    feed_stale_after_seconds: int = 30
    notification_max_attempts: int = 3
    notification_expiry_minutes: int = 15

    @field_validator("fallback_provider", "firebase_credentials_file", mode="before")
    @classmethod
    def _empty_to_none(cls, value: object) -> object:
        # "FALLBACK_PROVIDER=" in .env means "not set".
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("database_url", "test_database_url", mode="before")
    @classmethod
    def _use_asyncpg(cls, value: object) -> object:
        # Supabase, Render and Neon hand out "postgresql://..." URLs; we need the async driver.
        if isinstance(value, str):
            for prefix in ("postgres://", "postgresql://"):
                if value.startswith(prefix):
                    return "postgresql+asyncpg://" + value.removeprefix(prefix)
        return value

    @model_validator(mode="after")
    def _check_production_safety(self) -> "Settings":
        if self.environment == "production" and self.auth_dev_mode:
            raise ValueError("AUTH_DEV_MODE must be false when ENVIRONMENT=production")
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def angelone_configured(self) -> bool:
        return all(
            [
                self.angelone_api_key,
                self.angelone_client_code,
                self.angelone_pin.get_secret_value(),
                self.angelone_totp_secret.get_secret_value(),
            ]
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
