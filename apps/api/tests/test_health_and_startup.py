# Purpose: verify health/readiness probes and production startup guards.
# Responsibilities: confirm liveness is dependency-free, readiness reports Redis/database state, and
#   validate_runtime fails closed on unsafe production configuration (in-memory backends, missing or
#   unreachable Redis). Dependencies: the test client factory and Settings.
from __future__ import annotations

import pytest

from app.config.settings import Settings


def test_health_is_ok(client) -> None:  # type: ignore[no-untyped-def]
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ready_reports_dependencies(client) -> None:  # type: ignore[no-untyped-def]
    body = client.get("/ready").json()
    assert body["database"]["status"] == "ok"
    # Tests run against an in-process fakeredis server, so the replay backend reports healthy.
    assert body["redis"]["status"] in {"ok", "not_required"}


def _prod_settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "database_url": "postgresql+psycopg://u:p@localhost/db",
        "app_env": "production",
        "rate_limit_mode": "gateway",
        "replay_backend": "redis",
        "redis_url": "fakeredis://startup-tests",
        "evidence_encryption_mode": "local",
        "monitor_signature_required": True,
        "auth_enabled": True,
        # Pinned so a local .env cannot leak surface flags into a production assertion.
        "demo_enabled": False,
        "judge_workspace_enabled": False,
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def test_production_requires_redis_replay_backend() -> None:
    with pytest.raises(RuntimeError, match="replay protection requires REPLAY_BACKEND=redis"):
        _prod_settings(replay_backend="memory").validate_runtime()


def test_production_app_rate_limit_requires_redis_backend() -> None:
    with pytest.raises(RuntimeError, match="app-level rate limiting requires"):
        _prod_settings(rate_limit_mode="app", rate_limit_backend="memory").validate_runtime()


def test_production_redis_backend_requires_url() -> None:
    with pytest.raises(RuntimeError, match="REDIS_URL is required"):
        _prod_settings(redis_url=None).validate_runtime()


def test_production_requires_evidence_encryption_mode() -> None:
    with pytest.raises(RuntimeError, match="EVIDENCE_ENCRYPTION_MODE"):
        _prod_settings(evidence_encryption_mode="disabled").validate_runtime()


def test_production_startup_fails_when_redis_unreachable() -> None:
    with pytest.raises(RuntimeError, match="Redis is unavailable at startup"):
        _prod_settings(
            rate_limit_mode="app",
            rate_limit_backend="redis",
            redis_url="redis://127.0.0.1:6399",  # nothing listening here
        ).validate_runtime()


def test_production_requires_monitor_signatures() -> None:
    with pytest.raises(RuntimeError, match="MONITOR_SIGNATURE_REQUIRED=true"):
        _prod_settings(monitor_signature_required=False).validate_runtime()


def test_staging_requires_monitor_signatures() -> None:
    with pytest.raises(RuntimeError, match="MONITOR_SIGNATURE_REQUIRED=true"):
        _prod_settings(app_env="staging", monitor_signature_required=False).validate_runtime()


def test_production_starts_with_signatures_enabled() -> None:
    # A fully-configured production setup (signatures on, redis replay, encryption) validates.
    _prod_settings(monitor_signature_required=True).validate_runtime()


def test_development_allows_signatures_disabled() -> None:
    # Migration-friendly: development may run with signatures off.
    Settings(
        database_url="postgresql+psycopg://u:p@localhost/db",  # type: ignore[arg-type]
        app_env="development",
        monitor_signature_required=False,
    ).validate_runtime()


def test_production_compose_enables_monitor_signatures() -> None:
    from pathlib import Path

    compose = Path(__file__).resolve().parents[3] / "docker-compose.prod.example.yml"
    text = compose.read_text(encoding="utf-8")
    assert "MONITOR_SIGNATURE_REQUIRED: 'true'" in text


def test_readiness_reports_signature_enforcement(client) -> None:  # type: ignore[no-untyped-def]
    body = client.get("/ready").json()
    assert "monitor_signatures_enforced" in body
    # No secrets/signatures/nonces leak through the readiness surface.
    assert "signature" not in body and "secret" not in body and "nonce" not in body


def test_development_skips_all_guards() -> None:
    # Development returns early: unsafe backends are permitted for local single-worker use.
    Settings(
        database_url="postgresql+psycopg://u:p@localhost/db",  # type: ignore[arg-type]
        app_env="development",
        replay_backend="memory",
        rate_limit_backend="memory",
        evidence_encryption_mode="disabled",
    ).validate_runtime()
