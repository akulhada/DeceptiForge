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
    cors_allow_credentials: bool = False
    demo_enabled: bool = False
    auth_enabled: bool = True
    demo_api_key: str | None = None
    # Maps an API key to the single organization it may act as (env: API_KEY_BINDINGS as JSON).
    api_key_bindings: dict[str, str] = Field(default_factory=dict)
    incident_narrative_enabled: bool = True
    narrative_cooldown_seconds: int = 30
    openai_api_key: str | None = None
    openai_incident_model: str = "gpt-4o-mini"
    # Abuse / resource limits (single-process MVP; production needs edge enforcement).
    max_request_body_bytes: int = 1_048_576
    max_artifact_bytes: int = 2_097_152
    monitoring_max_value_bytes: int = 65_536
    monitoring_rate_limit_per_minute: int = 60
    narrative_rate_limit_per_minute: int = 10
    narrative_revision_retention_count: int = 20
    monitoring_event_retention_days: int = 30
    incident_stale_after_seconds: int = 86_400
    monitoring_timestamp_skew_seconds: int = 300
    # Rate limiting: "app" uses the in-process limiter (single worker only); "gateway" delegates to
    # an edge/reverse-proxy. Production with "app" requires REDIS_URL (distributed store).
    rate_limit_mode: str = "app"
    redis_url: str | None = None

    def validate_runtime(self) -> None:
        """Fail fast on unsafe production configuration."""
        if self.is_development:
            return
        if self.rate_limit_mode == "app" and self.redis_url is None:
            raise RuntimeError(
                "production app-level rate limiting requires REDIS_URL, "
                "or set RATE_LIMIT_MODE=gateway to delegate to the edge"
            )

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
