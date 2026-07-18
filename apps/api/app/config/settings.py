# Purpose: load validated application configuration.
# Responsibilities: define the API's current environment contract.
# Future modules: add settings alongside their integration owner.
from functools import lru_cache

from pydantic import Field, PostgresDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Environment-derived settings required by the infrastructure layer."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    app_name: str = "DeceptiForge API"
    app_env: str = "production"
    log_level: str = "INFO"
    database_url: PostgresDsn
    cors_origins: list[str] = Field(default_factory=list)
    demo_enabled: bool = False

    @property
    def is_development(self) -> bool:
        """Return whether developer diagnostics may be enabled."""
        return self.app_env == "development"

    @property
    def allows_local_path_scan(self) -> bool:
        """Only local development may accept arbitrary server filesystem paths.

        Demo routes scan their fixed bundled fixture internally. DEMO_ENABLED must not reopen the
        generic scan endpoint in a production-like demo deployment.
        """
        return self.is_development


@lru_cache
def get_settings() -> Settings:
    """Cache one validated settings object per process."""
    return Settings()
