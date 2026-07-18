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
    auth_enabled: bool = True
    demo_api_key: str | None = None
    incident_narrative_enabled: bool = True
    narrative_cooldown_seconds: int = 30
    openai_api_key: str | None = None
    openai_incident_model: str = "gpt-4o-mini"

    @property
    def openai_configured(self) -> bool:
        """GPT narratives are attempted only when a key is present and the feature is on."""
        return self.incident_narrative_enabled and bool(self.openai_api_key)

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
