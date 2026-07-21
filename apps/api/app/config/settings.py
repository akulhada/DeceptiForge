# Purpose: load validated application configuration.
# Responsibilities: define the API's current environment contract.
# Future modules: add settings alongside their integration owner.
from datetime import datetime
from functools import lru_cache

from pydantic import Field, PostgresDsn, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# The deployment modes DeceptiForge recognises. Only `development` relaxes security controls;
# `judge` is a hosted demonstration environment and is deliberately production-like — it inherits
# every startup guard (auth required, Redis fail-closed, signed ingestion, no filesystem scanning)
# and differs from production only in which demonstration surfaces may be mounted.
DEPLOYMENT_MODES = frozenset({"development", "test", "judge", "staging", "production"})

# Environments where the curated demo story may be mounted, and only with DEMO_ENABLED=true.
_DEMO_MODES = frozenset({"development", "judge"})

# The restricted judge workspace: development builds it, judge hosts it, tenants never see it.
_JUDGE_WORKSPACE_MODES = frozenset({"development", "judge"})

# The Analysis Lab is an internal fixture surface. It is never mounted in a hosted environment.
_ANALYSIS_LAB_MODES = frozenset({"development", "test"})


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
    # Interactive Demo Lab preview analysis: read-only but compute-bearing, so it gets its own
    # per-organization+actor budget rather than reusing the monitoring-ingest limit.
    # The Interactive Analysis Lab is a demonstration/testing surface, not a production capability.
    # Off by default and refused outside development even when explicitly enabled.
    # Operational readiness thresholds for asynchronous reconstruction work. These gate
    # /ready/operational only — never HTTP instance readiness.
    worker_max_queue_age_seconds: int = 900
    worker_max_failed_jobs: int = 50
    analysis_lab_enabled: bool = False
    analysis_preview_rate_limit_per_minute: int = 30

    # ---- restricted judge workspace -------------------------------------------------------------
    # Budgets are per SANDBOX SESSION rather than sliding windows: a session is already TTL-bound,
    # so a spent budget is bounded in time by the session itself. Quota accounting deliberately
    # survives reset — resetting the sandbox restores its data, not its budget.
    judge_workspace_enabled: bool = False
    judge_sandbox_ttl_hours: int = 8
    judge_max_analysis_runs: int = 50
    judge_max_interactions: int = 10
    judge_max_exports: int = 20
    # Reset is the one action worth pacing: it deletes and re-seeds, so a tight loop is expensive.
    judge_reset_cooldown_seconds: int = 60

    # ---- Controlled learning + calibration ------------------------------------------------------
    # Off by default. Learning only ever records normalized features/outcomes and produces CANDIDATE
    # weights; nothing reaches production without human approval (LEARNING_REQUIRE_APPROVAL).
    learning_enabled: bool = False
    learning_event_retention_days: int = 180
    learning_min_events_for_calibration: int = 50
    learning_min_distinct_outcomes: int = 10
    # Distinct human actors required before analyst feedback can move a weight (anti-poisoning).
    learning_min_distinct_actors: int = 3
    # Maximum share of a single cohort's evidence one actor may contribute (anti-poisoning).
    learning_max_actor_contribution: float = 0.34
    learning_calibration_interval_hours: int = 24
    learning_require_approval: bool = True
    learning_org_specific_enabled: bool = False
    global_aggregate_learning_enabled: bool = False
    learning_min_global_cohort_size: int = 25
    learning_max_feedback_comment_length: int = 500
    learning_methodology_version: str = "calibration-v1"
    learning_feedback_rate_limit_per_minute: int = 20
    # Outcome attribution: a placement is never scored negatively before these are satisfied.
    learning_min_observation_hours: int = 72
    learning_min_healthy_monitoring_ratio: float = 0.8
    external_intelligence_enabled: bool = False
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
    # Browser AI-paste sensors. Disabled by default; explicit per-environment enablement.
    browser_sensor_enabled: bool = False
    browser_sensor_enrollment_ttl_seconds: int = 900
    browser_sensor_event_queue_limit: int = 200
    browser_sensor_policy_sync_seconds: int = 300
    browser_sensor_trace_sync_seconds: int = 300
    browser_sensor_allowed_domains: list[str] = Field(default_factory=list)
    browser_sensor_require_signed_policy: bool = False
    browser_sensor_min_extension_version: str = "0.1.0"
    browser_sensor_max_registry_entries: int = 5_000
    browser_sensor_max_event_metadata_bytes: int = 1_024
    # AI agent activity sensors. Disabled by default; detect-only; explicit enablement outside dev.
    agent_sensor_enabled: bool = False
    agent_sensor_mode: str = "detect"
    agent_sensor_event_max_bytes: int = 8_192
    agent_sensor_queue_limit: int = 500
    agent_session_max_duration_hours: int = 24
    agent_event_retention_days: int = 30
    agent_scope_max_allowed_paths: int = 200
    agent_scope_max_denied_paths: int = 200
    agent_sensor_min_version: str = "0.1.0"
    require_signed_agent_events: bool = True
    # Measured coverage engine. Disabled by default; explicit per-environment enablement.
    coverage_engine_enabled: bool = False
    coverage_calculation_interval_minutes: int = 60
    coverage_verification_max_age_hours: int = 168
    coverage_max_unknown_weight: float = 0.4
    coverage_min_acceptable_score: float = 0.6
    coverage_max_recommendations: int = 25
    coverage_methodology_version: str = "coverage-v1"
    # SIEM/SOAR security integrations. Disabled by default; explicit enablement outside dev.
    security_integrations_enabled: bool = False
    security_export_max_payload_bytes: int = 65_536
    security_export_max_batch_size: int = 50
    security_export_timeout_seconds: int = 10
    security_export_max_attempts: int = 6
    security_export_max_age_hours: int = 72
    security_export_allowed_domains: list[str] = Field(default_factory=list)
    security_export_allow_private_networks: bool = False
    security_export_default_profile: str = "minimal"
    security_export_worker_batch_size: int = 20
    security_export_worker_lease_seconds: int = 60
    security_export_delivery_retention_days: int = 14
    security_export_dead_letter_retention_days: int = 90
    # Multi-region reliability / disaster recovery. Region identity + fencing + failover controls.
    deployment_region: str = "local"
    cluster_id: str = "local"
    cluster_role: str = "primary"  # primary | standby | recovery
    active_region_epoch: int = 1
    dr_enabled: bool = False
    secondary_region: str = ""
    database_cluster_id: str = "local"
    deployment_revision: str = "dev"
    backup_verification_enabled: bool = False
    restore_drill_enabled: bool = False
    postgres_rpo_target_minutes: int = 5
    postgres_rto_target_minutes: int = 60
    worker_stale_lease_seconds: int = 300
    regional_failover_requires_approval: bool = True
    schedulers_enabled: bool = True
    external_side_effects_enabled: bool = True
    maintenance_mode: bool = False
    # Performance and capacity policy. The defaults are deliberately conservative until a staging
    # certification records measured throughput for the deployed topology.
    performance_testing_enabled: bool = False
    capacity_management_enabled: bool = False
    default_tenant_tier: str = "small"
    monitoring_max_events_per_second: int = 20
    monitoring_max_burst: int = 50
    tenant_max_pending_jobs: int = 1_000
    tenant_max_concurrent_scans: int = 2
    tenant_max_concurrent_deployments: int = 2
    tenant_max_report_jobs: int = 2
    worker_priority_reserve_percent: int = 30
    api_database_pool_size: int = 10
    worker_database_pool_size: int = 5
    queue_backlog_alert_seconds: int = 300
    capacity_headroom_percent: int = 40
    performance_methodology_version: str = "performance-v1"
    onboarding_enabled: bool = False
    onboarding_version: str = "onboarding-v1"
    onboarding_reconciliation_interval_minutes: int = 30
    onboarding_detection_test_enabled: bool = False
    onboarding_require_siem_for_activation: bool = False
    onboarding_require_sso_for_activation: bool = True
    onboarding_min_coverage_score: float = 0.0
    onboarding_safe_first_decoy_types: list[str] = Field(
        default_factory=lambda: ["document", "repository_config", "database_record"]
    )
    product_analytics_enabled: bool = False

    @property
    def is_active_write_region(self) -> bool:
        """Only the primary role may accept authoritative writes and run side-effect workers."""
        return self.cluster_role == "primary"

    @model_validator(mode="after")
    def _validate_cluster_role(self) -> "Settings":
        # A typo in APP_ENV must not silently select the most permissive behaviour. Every
        # environment-dependent guard keys off this value, so an unrecognised mode is rejected
        # rather than treated as "not development" by accident.
        if self.app_env not in DEPLOYMENT_MODES:
            raise ValueError(f"app_env must be one of {sorted(DEPLOYMENT_MODES)}")
        # Ambiguous cluster-role configuration is rejected everywhere; production must be explicit.
        if self.cluster_role not in {"primary", "standby", "recovery"}:
            raise ValueError("cluster_role must be one of primary, standby, recovery")
        prod_dr = self.dr_enabled and self.app_env in {"staging", "production"}
        if prod_dr and not self.secondary_region:
            raise ValueError("secondary_region is required when dr_enabled in staging/production")
        if self.default_tenant_tier not in {"small", "medium", "large"}:
            raise ValueError("default_tenant_tier must be small, medium, or large")
        if not 0 <= self.worker_priority_reserve_percent < 100:
            raise ValueError("worker_priority_reserve_percent must be in [0, 100)")
        if self.monitoring_max_events_per_second <= 0 or self.monitoring_max_burst <= 0:
            raise ValueError("monitoring event limits must be positive")
        if self.monitoring_max_burst < self.monitoring_max_events_per_second:
            raise ValueError("monitoring_max_burst must be at least events per second")
        if self.api_database_pool_size <= 0 or self.worker_database_pool_size <= 0:
            raise ValueError("database pool sizes must be positive")
        if self.onboarding_reconciliation_interval_minutes <= 0:
            raise ValueError("onboarding reconciliation interval must be positive")
        if not 0 <= self.onboarding_min_coverage_score <= 1:
            raise ValueError("onboarding minimum coverage score must be in [0, 1]")
        return self

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
        if self.analysis_lab_enabled and not self.allows_analysis_lab:
            raise RuntimeError(
                f"ANALYSIS_LAB_ENABLED=true is not permitted in {self.app_env}; the analysis lab "
                "is an internal fixture surface and must return 404 in judge, staging and "
                "production"
            )
        # P0: security controls must never fail open outside development. A Redis outage must
        # refuse signed ingestion and deny rate-limited requests, not silently admit them.
        if self.redis_fail_mode != "closed":
            raise RuntimeError(
                "REDIS_FAIL_MODE must be 'closed' outside development; failing open would let "
                "replay protection and rate limiting silently admit requests during a Redis outage"
            )
        # A deployment with authentication disabled is operationally unusable (every protected route
        # returns 401) and must not be reported as a healthy running service.
        if not self.auth_enabled:
            raise RuntimeError(
                "AUTH_ENABLED=false is not permitted outside development; every protected route "
                "would reject requests while the deployment reported itself healthy"
            )
        if self.capacity_management_enabled and self.redis_url is None:
            raise RuntimeError(
                "capacity management requires REDIS_URL for shared tenant quota enforcement"
            )
        # Calibration must never silently reach production: approval is mandatory outside
        # development, and cross-tenant aggregation requires an explicit reviewed decision.
        if self.learning_enabled and not self.learning_require_approval:
            raise RuntimeError(
                "LEARNING_REQUIRE_APPROVAL=false is not permitted outside development; "
                "candidate weights must be human-approved before activation"
            )
        if self.global_aggregate_learning_enabled and self.learning_min_global_cohort_size < 10:
            raise RuntimeError(
                "global aggregate learning requires LEARNING_MIN_GLOBAL_COHORT_SIZE >= 10 to "
                "prevent rare-category re-identification"
            )
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
        # Checked last so that a security misconfiguration is always reported first. The demo story
        # is fictional but still a write surface driving the real pipeline, so it may exist only in
        # development and in the hosted judge environment.
        if self.judge_workspace_enabled and not self.allows_judge_workspace:
            raise RuntimeError(
                f"JUDGE_WORKSPACE_ENABLED=true is not permitted in {self.app_env}; the sandbox "
                "provisions organizations and deletes records, which has no place in a tenant "
                "deployment"
            )
        if self.demo_enabled and not self.allows_demo_surface:
            raise RuntimeError(
                f"DEMO_ENABLED=true is not permitted in {self.app_env}; the curated demo story is "
                "available only in development and in the hosted judge environment"
            )

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
    def is_judge(self) -> bool:
        """Whether this is the hosted judge environment.

        Judge mode is NOT a development mode. It is internet-reachable and therefore keeps every
        production security control; the only thing it relaxes is which demonstration surfaces may
        be mounted. Nothing should branch on this property to weaken a security decision.
        """
        return self.app_env == "judge"

    @property
    def is_production_like(self) -> bool:
        """Environments that share the hardened runtime contract (no dev conveniences).

        Judge is included: it is hosted, so unsigned ingestion, fail-open Redis, disabled auth and
        filesystem scanning are as unacceptable there as in production.
        """
        return self.app_env in {"judge", "staging", "production"}

    @property
    def allows_demo_surface(self) -> bool:
        """Whether the curated demo story may be mounted at all in this environment.

        DEMO_ENABLED is still required on top of this; the environment only decides eligibility.
        Staging and production always refuse, so the demo cannot appear on a real tenant
        deployment even if the flag is set.
        """
        return self.app_env in _DEMO_MODES

    @property
    def allows_judge_workspace(self) -> bool:
        """Whether the restricted judge workspace may be mounted.

        Development (for building it) and judge (its purpose). A tenant deployment never exposes it:
        the sandbox provisions organizations and deletes records, which has no place in production.
        """
        return self.app_env in _JUDGE_WORKSPACE_MODES

    @property
    def allows_analysis_lab(self) -> bool:
        """Whether the Analysis Lab may be mounted. Development and test only — never hosted."""
        return self.app_env in _ANALYSIS_LAB_MODES

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
