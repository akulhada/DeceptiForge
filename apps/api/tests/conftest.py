# Purpose: configure API tests with an isolated in-memory database and per-test settings.
# Responsibilities: satisfy settings validation, bind SQLAlchemy to SQLite, override the
#   request-scoped session, and build the app under a chosen DEMO_ENABLED/APP_ENV so gating and
#   scan-hardening can be exercised. Dependencies: FastAPI test client.
from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager

os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://unused:unused@localhost/deceptiforge")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config.settings import get_settings
from app.database.base import Base
from app.dependencies import get_db
from app.models import records as _records  # noqa: F401  (register tables)

# Modes that share the hardened runtime contract. Kept in sync with Settings.is_production_like.
_PRODUCTION_LIKE_MODES = {"judge", "staging", "production"}


@contextmanager
def build_client(
    *,
    demo_enabled: bool = True,
    app_env: str = "development",
    auth_enabled: bool = False,
    demo_api_key: str = "local-development-key",
    api_key_bindings: str = "{}",
    cors_origins: str | None = None,
    cors_allow_credentials: bool = False,
    capacity_management_enabled: bool = False,
    monitor_signature_required: bool | None = None,
    bootstrap_keys_enabled: bool | None = None,
    bootstrap_expires_at: str | None = None,
    decoy_deployment_enabled: bool = False,
    database_connectors_enabled: bool = False,
    database_honey_deployment_enabled: bool = False,
    rag_connectors_enabled: bool = False,
    mcp_connectors_enabled: bool = False,
    ai_tripwire_deployment_enabled: bool = False,
    browser_sensor_enabled: bool = False,
    agent_sensor_enabled: bool = False,
    coverage_engine_enabled: bool = False,
    security_integrations_enabled: bool = False,
    onboarding_enabled: bool = False,
    onboarding_detection_test_enabled: bool = False,
    learning_enabled: bool = False,
    analysis_lab_enabled: bool = False,
) -> Iterator[TestClient]:
    # Production-like environments must enforce signatures; default the flag on there unless a test
    # explicitly overrides it. Development defaults off (migration-friendly). Derived from the
    # settings contract rather than a literal set so a new hosted mode cannot be tested unsigned.
    if monitor_signature_required is None:
        monitor_signature_required = app_env in _PRODUCTION_LIKE_MODES
    overrides = {
        "DEMO_ENABLED": "true" if demo_enabled else "false",
        "APP_ENV": app_env,
        "AUTH_ENABLED": "true" if auth_enabled else "false",
        "DEMO_API_KEY": demo_api_key,
        "API_KEY_BINDINGS": api_key_bindings,
        "CORS_ORIGINS": cors_origins if cors_origins is not None else "[]",
        "CORS_ALLOW_CREDENTIALS": "true" if cors_allow_credentials else "false",
        "CAPACITY_MANAGEMENT_ENABLED": "true" if capacity_management_enabled else "false",
        "MONITOR_SIGNATURE_REQUIRED": "true" if monitor_signature_required else "false",
        "DECOY_DEPLOYMENT_ENABLED": "true" if decoy_deployment_enabled else "false",
        "DATABASE_CONNECTORS_ENABLED": "true" if database_connectors_enabled else "false",
        "DATABASE_HONEY_DEPLOYMENT_ENABLED": (
            "true" if database_honey_deployment_enabled else "false"
        ),
        "RAG_CONNECTORS_ENABLED": "true" if rag_connectors_enabled else "false",
        "MCP_CONNECTORS_ENABLED": "true" if mcp_connectors_enabled else "false",
        "AI_TRIPWIRE_DEPLOYMENT_ENABLED": ("true" if ai_tripwire_deployment_enabled else "false"),
        "BROWSER_SENSOR_ENABLED": "true" if browser_sensor_enabled else "false",
        "AGENT_SENSOR_ENABLED": "true" if agent_sensor_enabled else "false",
        "COVERAGE_ENGINE_ENABLED": "true" if coverage_engine_enabled else "false",
        "SECURITY_INTEGRATIONS_ENABLED": "true" if security_integrations_enabled else "false",
        "LEARNING_ENABLED": "true" if learning_enabled else "false",
        "ANALYSIS_LAB_ENABLED": "true" if analysis_lab_enabled else "false",
        "ONBOARDING_ENABLED": "true" if onboarding_enabled else "false",
        "ONBOARDING_DETECTION_TEST_ENABLED": (
            "true" if onboarding_detection_test_enabled else "false"
        ),
        # Tests exercise production settings; delegate rate limiting to the edge so create_app
        # does not require a Redis-backed rate-limit store.
        "RATE_LIMIT_MODE": "gateway",
        # Replay protection is exercised against an in-process fakeredis server so the Redis path is
        # covered without an external service; the URL scheme is resolved by redis_support.
        "REPLAY_BACKEND": "redis",
        "REDIS_URL": "fakeredis://deceptiforge-tests",
        # A non-disabled encryption mode is required for production startup validation.
        "EVIDENCE_ENCRYPTION_MODE": "local",
        "EVIDENCE_ENCRYPTION_KEY": "test-evidence-key-0000000000000000000000",
    }
    # Tests that provision env bindings exercise the (time-boxed) bootstrap window; open it by
    # default so bound keys authenticate and production startup validation passes. Individual tests
    # can override the flag/expiry to exercise the disabled/expired paths.
    if api_key_bindings not in ("{}", ""):
        overrides["BOOTSTRAP_KEYS_ENABLED"] = "true"
        overrides["BOOTSTRAP_EXPIRES_AT"] = "2999-01-01T00:00:00+00:00"
    if bootstrap_keys_enabled is not None:
        overrides["BOOTSTRAP_KEYS_ENABLED"] = "true" if bootstrap_keys_enabled else "false"
    if bootstrap_expires_at is not None:
        overrides["BOOTSTRAP_EXPIRES_AT"] = bootstrap_expires_at
    previous = {key: os.environ.get(key) for key in overrides}
    os.environ.update(overrides)
    get_settings.cache_clear()
    from app.services.rate_limit import reset_rate_limiter
    from app.services.redis_support import reset_clients_for_tests
    from app.services.replay import reset_replay_guard

    reset_clients_for_tests()
    reset_rate_limiter()
    reset_replay_guard()

    from app.main import create_app

    # create_app() runs startup validation, which may raise (e.g. an unsafe production config). Keep
    # it inside the try/finally so the environment is always restored — otherwise a raising build
    # would leak overrides (like AUTH_ENABLED=false) into later tests.
    try:
        application = create_app()
        engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        Base.metadata.create_all(engine)
        testing_session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

        def override_get_db() -> Iterator[Session]:
            session = testing_session()
            try:
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise
            finally:
                session.close()

        application.dependency_overrides[get_db] = override_get_db
        with TestClient(application) as test_client:
            # Expose the test session factory so tests can seed rows (e.g. API keys).
            test_client.app_session = testing_session  # type: ignore[attr-defined]
            yield test_client
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        get_settings.cache_clear()
        get_settings.cache_clear()


@pytest.fixture
def client() -> Iterator[TestClient]:
    with build_client(demo_enabled=True) as test_client:
        yield test_client


@pytest.fixture
def make_client():
    """Factory for building a client under specific settings (as a context manager)."""
    return build_client
