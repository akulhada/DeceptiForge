# Purpose: load validated application configuration. Responsibilities: define the API's current environment contract. Future modules: add settings alongside their integration owner.
from functools import lru_cache

from pydantic import Field, PostgresDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-derived settings required by the infrastructure layer."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    app_name: str = "DeceptiForge API"
    app_env: str = "development"
    log_level: str = "INFO"
    database_url: PostgresDsn
    cors_origins: list[str] = Field(default_factory=list)

    @property
    def is_development(self) -> bool:
        """Return whether developer diagnostics may be enabled."""
        return self.app_env == "development"


@lru_cache
def get_settings() -> Settings:
    """Cache one validated settings object per process."""
    return Settings()
