"""Environment-backed application settings."""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: Literal["development", "test", "production"] = "development"
    database_url: str = "postgresql+psycopg://gtm_state:gtm_state_local@localhost:5432/gtm_state"


@lru_cache
def get_settings() -> Settings:
    """Return one validated settings object per process."""

    return Settings()
