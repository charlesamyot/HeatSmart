"""Application configuration via pydantic-settings and YAML rate file."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(Path(__file__).resolve().parents[2] / "config" / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # EcoNet credentials (required at runtime, loaded from .env)
    econet_email: str = Field(default="", description="EcoNet account email")
    econet_password: str = Field(default="", description="EcoNet account password")

    # Fernet key for encrypting credentials persisted to disk
    encryption_key: str = Field(default="", description="Fernet encryption key")

    # Polling intervals
    state_poll_interval: int = Field(default=300, description="State poll interval in seconds")
    energy_poll_interval: int = Field(default=1800, description="Energy poll interval in seconds")

    # Database
    database_path: str = Field(default="config/econet_data.db")

    # Temperature safety bounds (enforced server-side on all control requests)
    min_setpoint: float = Field(default=110.0)
    max_setpoint: float = Field(default=140.0)

    # Timezone: ClearBlade registers device as America/New_York by default
    # but the device is actually in Seattle. Energy hours from API are in device_tz.
    device_timezone: str = Field(default="America/New_York", description="TZ the API reports hours in")
    local_timezone: str = Field(default="America/Los_Angeles", description="Your actual timezone")

    # Supabase
    supabase_url: str = Field(default="", description="Supabase project URL")
    supabase_key: str = Field(default="", description="Supabase anon/public key")
    supabase_jwt_secret: str = Field(default="", description="Supabase JWT secret for token verification")

    # Stripe
    stripe_secret_key: str = Field(default="", description="Stripe secret key")
    stripe_webhook_secret: str = Field(default="", description="Stripe webhook signing secret")

    # Database URL (PostgreSQL on Render/Supabase, or SQLite locally)
    database_url: str = Field(default="", description="PostgreSQL connection string (overrides database_path)")

    # Rates config path
    rates_config_path: str = Field(
        default=str(Path(__file__).resolve().parents[2] / "config" / "default_rates.yaml")
    )

    @field_validator("econet_email", "econet_password", mode="before")
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        return v.strip() if isinstance(v, str) else v

    @property
    def has_credentials(self) -> bool:
        return bool(self.econet_email and self.econet_password)


@lru_cache
def get_settings() -> Settings:
    return Settings()


def load_tou_rates() -> dict:
    """Load TOU rate schedule from YAML config file."""
    settings = get_settings()
    path = settings.rates_config_path
    if not os.path.exists(path):
        raise FileNotFoundError(f"TOU rates config not found: {path}")
    with open(path) as f:
        return yaml.safe_load(f)
