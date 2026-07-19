# Purpose: load validated application configuration.
# Responsibilities: define the API's current environment contract.
# Future modules: add settings alongside their integration owner.
from datetime import datetime
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
    admin_rate_limit_per_minute: int = 30
    narrative_revision_retention_count: int = 20
    monitoring_event_retention_days: int = 30
    alert_retention_days: int = 90
    api_key_retention_days: int = 30
    reconstruction_job_retention_days: int = 7
    incident_archive_after_seconds: int = 2_592_000  # 30 days after last activity
    retention_batch_size: int = 500
    incident_stale_after_seconds: int = 86_400
    monitoring_timestamp_skew_seconds: int = 300
    # When true, monitoring ingestion requires a valid monitor-signature-v1 HMAC signature. Kept off
    # by default so existing deployments migrate deliberately; production examples enable it.
    monitor_signature_required: bool = False
    # Rate limiting: "app" uses an application-level limiter; "gateway" delegates to an
    # edge/reverse-proxy. In "app" mode the backend below selects the store.
    rate_limit_mode: str = "app"
    # Distributed-store selection. "memory" is single-worker only (development/tests); "redis"
    # coordinates across replicas. Production must not silently run "memory" for app-enforced limits
    # or for replay protection.
    rate_limit_backend: str = "memory"
    replay_backend: str = "memory"
    redis_url: str | None = None
    redis_key_prefix: str = "deceptiforge"
    redis_socket_timeout_seconds: float = 2.0
    redis_connect_timeout_seconds: float = 2.0
    # Behavior when a required Redis is unreachable at request time: "closed" rejects (safe default)
    # and "open" degrades to allowing the request. Startup still fails if Redis is required + down.
    redis_fail_mode: str = "closed"
    # Evidence encryption boundary. "disabled" (development only) stores plaintext; production must
    # set an explicit mode (e.g. "local" for an app-managed key, or a documented KMS strategy).
    evidence_encryption_mode: str = "disabled"
    evidence_encryption_key: str | None = None
    # Bootstrap keys (API_KEY_BINDINGS) grant owner scope without a DB row. Disabled by default;
    # a one-time bootstrap window must be explicitly opened, is time-boxed via BOOTSTRAP_EXPIRES_AT,
    # and must be closed once the first DB-backed owner key exists.
    bootstrap_keys_enabled: bool = False
    bootstrap_expires_at: datetime | None = None
    # Decoy deployment (approval + lifecycle). Disabled by default; must be explicitly enabled per
    # environment so the repository-writing feature never activates accidentally.
    decoy_deployment_enabled: bool = False
    require_separate_deployment_approver: bool = True
    decoy_max_files_per_deployment: int = 25
    decoy_max_bytes_per_deployment: int = 262_144
    decoy_allowed_path_prefixes: list[str] = Field(
        default_factory=lambda: ["docs/", "runbooks/", "config/decoys/", ".deceptiforge/"]
    )
    decoy_protected_path_patterns: list[str] = Field(
        default_factory=lambda: [
            ".env",
            "secret",
            "credential",
            ".pem",
            ".key",
            "id_rsa",
            ".github/workflows/",
            "package-lock.json",
            "pnpm-lock.yaml",
            "yarn.lock",
            "Gemfile.lock",
        ]
    )
    decoy_default_expiry_days: int = 90
    decoy_pr_detail_level: str = "standard"  # minimal | standard | full
    # Database honey records (PostgreSQL connectors + synthetic rows). Disabled by default;
    # must be explicitly enabled per environment so the database-writing feature never activates
    # accidentally.
    database_connectors_enabled: bool = False
    database_honey_deployment_enabled: bool = False
    database_require_tls: bool = True
    database_connect_timeout_seconds: int = 10
    database_statement_timeout_ms: int = 5_000
    database_max_schema_tables: int = 2_000
    database_max_deployment_rows: int = 25
    database_default_expiry_days: int = 90
    require_separate_database_approver: bool = True
    # AI/RAG/MCP tripwire sensors. Disabled by default; explicit per-environment enablement.
    ai_tripwire_deployment_enabled: bool = False
    rag_connectors_enabled: bool = False
    mcp_connectors_enabled: bool = False
    ai_tripwire_default_expiry_days: int = 90
    ai_tripwire_max_document_bytes: int = 16_384
    require_separate_ai_tripwire_approver: bool = True
    ai_tripwire_allowed_collections: list[str] = Field(
        default_factory=lambda: ["deceptiforge_decoys"]
    )
    ai_tripwire_allowed_mcp_servers: list[str] = Field(default_factory=list)
    database_allowed_schemas: list[str] = Field(default_factory=lambda: ["public"])
    database_blocked_table_patterns: list[str] = Field(
        default_factory=lambda: [
            "password",
            "credential",
            "secret",
            "token",
            "session",
            "auth",
            "payment",
            "card",
            "bank",
            "ssn",
            "tax",
            "health",
            "outbox",
            "event",
            "ledger",
            "queue",
            "webhook",
            "audit",
        ]
    )

    def bootstrap_active(self, now: datetime) -> bool:
        """Whether env bootstrap keys may authenticate right now."""
        if not self.bootstrap_keys_enabled:
            return False
        return self.bootstrap_expires_at is None or now < self.bootstrap_expires_at

    @property
    def _redis_required(self) -> bool:
        """Whether any app subsystem needs a shared Redis store in this configuration."""
        return (self.rate_limit_mode == "app" and self.rate_limit_backend == "redis") or (
            self.replay_backend == "redis"
        )

    def validate_runtime(self) -> None:
        """Fail fast on unsafe production configuration."""
        if self.is_development:
            return
        if self.rate_limit_mode == "app" and self.rate_limit_backend != "redis":
            raise RuntimeError(
                "production app-level rate limiting requires RATE_LIMIT_BACKEND=redis "
                "(with REDIS_URL), or set RATE_LIMIT_MODE=gateway to delegate to the edge"
            )
        if self.replay_backend != "redis":
            raise RuntimeError(
                "production replay protection requires REPLAY_BACKEND=redis with REDIS_URL; "
                "in-memory replay state is not shared across workers"
            )
        if self._redis_required and self.redis_url is None:
            raise RuntimeError("REDIS_URL is required when a Redis-backed backend is selected")
        if self.evidence_encryption_mode == "disabled":
            raise RuntimeError(
                "production requires an explicit EVIDENCE_ENCRYPTION_MODE (e.g. 'local' or a "
                "documented KMS/DB-level strategy); plaintext evidence is not permitted"
            )
        # Signed monitoring ingestion is mandatory in production-like environments (staging and
        # production). Development keeps the migration-friendly default (may be disabled).
        if not self.monitor_signature_required:
            raise RuntimeError(
                f"{self.app_env} requires MONITOR_SIGNATURE_REQUIRED=true; unsigned monitoring "
                "ingestion is not permitted outside development"
            )
        unrestricted_bootstrap = (
            self.bootstrap_keys_enabled
            and bool(self.api_key_bindings)
            and self.bootstrap_expires_at is None
        )
        if unrestricted_bootstrap:
            raise RuntimeError(
                "refusing to start: bootstrap API keys are enabled in production without an "
                "expiry; set BOOTSTRAP_EXPIRES_AT to time-box the window, then create a DB-backed "
                "owner key and set BOOTSTRAP_KEYS_ENABLED=false before restarting"
            )
        if self._redis_required:
            self._verify_redis_reachable()

    def _verify_redis_reachable(self) -> None:
        """Ping the configured Redis so startup fails fast when a required store is down."""
        from app.services.redis_support import RedisUnavailableError, ping_redis

        try:
            ping_redis(self)
        except RedisUnavailableError as error:
            raise RuntimeError(f"required Redis is unavailable at startup: {error}") from error

    @property
    def openai_configured(self) -> bool:
        """GPT narratives are attempted only when a key is present and the feature is on."""
        return self.incident_narrative_enabled and bool(self.openai_api_key)

    @property
    def is_development(self) -> bool:
        """Return whether developer diagnostics may be enabled."""
        return self.app_env == "development"

    @property
    def is_production_like(self) -> bool:
        """Staging and production share the hardened runtime contract (no dev conveniences)."""
        return self.app_env in {"staging", "production"}

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
    # Pydantic Settings resolves required fields from the environment, not constructor arguments.
    # The empty **kwargs unpack keeps this valid across mypy/plugin versions without a version-
    # dependent `type: ignore` (which some Python versions then flag as unused).
    return Settings(**{})
