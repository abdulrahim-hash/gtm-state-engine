"""Environment-backed application settings."""

from functools import lru_cache
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: Literal["development", "test", "production"] = "development"
    database_url: str = "postgresql+psycopg://gtm_state:gtm_state_local@localhost:5432/gtm_state"

    action_mutations_enabled: bool = False
    m5a_task_write_enabled: bool = False

    @model_validator(mode="after")
    def reject_production_action_mutations(self) -> "Settings":
        """Keep the hosted/production M1D surface read-only without authentication."""

        if self.app_env == "production" and self.action_mutations_enabled:
            raise ValueError("ACTION_MUTATIONS_ENABLED cannot be true when APP_ENV=production")
        if self.app_env == "production" and self.m5a_task_write_enabled:
            raise ValueError("M5A_TASK_WRITE_ENABLED cannot be true when APP_ENV=production")
        return self


@lru_cache
def get_settings() -> Settings:
    """Return one validated settings object per process."""

    return Settings()
