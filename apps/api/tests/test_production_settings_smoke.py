# Purpose: certify that the exact production-like configuration passes runtime validation and that
#   each unsafe deviation fails deterministically.
# Responsibilities: build Settings from the same names/values as docker-compose.prod.example.yml and
#   assert validate_runtime() accepts the safe config and rejects unsafe ones; assert auth bypass is
#   rejected at request time and demo routes are absent in production; assert the production Compose
#   file encodes the required topology. Never prints secrets. Dependencies: Settings, test client.
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.config.settings import Settings

_COMPOSE = Path(__file__).resolve().parents[3] / "docker-compose.prod.example.yml"

# The exact production-like values the deployment example configures for the API service.
_PROD: dict[str, object] = {
    "database_url": "postgresql+psycopg://ci:ci-test-only@postgres:5432/deceptiforge",
    "app_env": "production",
    "auth_enabled": True,
    "demo_enabled": False,
    # Pinned so a local .env cannot leak surface flags into a production assertion.
    "judge_workspace_enabled": False,
    "monitor_signature_required": True,
    "rate_limit_mode": "app",
    "rate_limit_backend": "redis",
    "replay_backend": "redis",
    "redis_fail_mode": "closed",
    "redis_url": "fakeredis://prod-smoke",
    "evidence_encryption_mode": "local",
    "evidence_encryption_key": "prod-smoke-evidence-key",
    "bootstrap_keys_enabled": False,
    "cors_origins": ["https://dashboard.example.com"],
}


def _settings(**overrides: object) -> Settings:
    return Settings(**{**_PROD, **overrides})  # type: ignore[arg-type]


def test_production_like_settings_validate() -> None:
    # The full production configuration must pass every startup guard.
    _settings().validate_runtime()


@pytest.mark.parametrize(
    ("overrides", "match"),
    [
        ({"monitor_signature_required": False}, "MONITOR_SIGNATURE_REQUIRED=true"),
        ({"replay_backend": "memory"}, "replay protection requires REPLAY_BACKEND=redis"),
        ({"rate_limit_backend": "memory"}, "app-level rate limiting requires"),
        ({"evidence_encryption_mode": "disabled"}, "EVIDENCE_ENCRYPTION_MODE"),
        ({"redis_url": None}, "REDIS_URL is required"),
        (
            {
                "bootstrap_keys_enabled": True,
                "api_key_bindings": {"k": "11111111-1111-1111-1111-111111111111"},
                "bootstrap_expires_at": None,
            },
            "bootstrap API keys are enabled in production",
        ),
    ],
)
def test_unsafe_production_settings_fail(overrides: dict[str, object], match: str) -> None:
    with pytest.raises(RuntimeError, match=match):
        _settings(**overrides).validate_runtime()


def test_time_boxed_bootstrap_is_allowed() -> None:
    # A bootstrap window with an expiry is the documented temporary-bootstrap path (still valid).
    _settings(
        bootstrap_keys_enabled=True,
        api_key_bindings={"k": "11111111-1111-1111-1111-111111111111"},
        bootstrap_expires_at=datetime.now(UTC) + timedelta(hours=1),
    ).validate_runtime()


# ---- request/router-level production guards (not startup) -----------------------------


def test_auth_bypass_rejected_in_production(make_client) -> None:  # type: ignore[no-untyped-def]
    # AUTH_ENABLED=false is a development-only bypass. Production now refuses to START with it,
    # rather than booting a deployment that reports healthy while rejecting every request.
    import pytest

    with pytest.raises(RuntimeError, match="AUTH_ENABLED"):
        with make_client(auth_enabled=False, app_env="production"):
            pass


def test_demo_routes_absent_in_production(make_client) -> None:  # type: ignore[no-untyped-def]
    # The demo surface is eligible only in development and judge, so production leaves it unmounted.
    with make_client(demo_enabled=False, app_env="production", auth_enabled=True) as client:
        assert client.post("/demo/seed").status_code == 404


def test_production_rejects_demo_enabled_at_startup(make_client) -> None:  # type: ignore[no-untyped-def]
    # Stronger than leaving the routes unmounted: the operator is told the configuration is invalid.
    with pytest.raises(RuntimeError, match="DEMO_ENABLED"):
        with make_client(demo_enabled=True, app_env="production", auth_enabled=True):
            pass


# ---- production Compose topology --------------------------------------------------------


def test_production_compose_encodes_safe_topology() -> None:
    text = _COMPOSE.read_text(encoding="utf-8")
    assert "MONITOR_SIGNATURE_REQUIRED: 'true'" in text
    assert "APP_ENV: production" in text
    assert "DEMO_ENABLED: 'false'" in text
    assert "RATE_LIMIT_BACKEND: redis" in text
    assert "REPLAY_BACKEND: redis" in text
    # Workers for reconstruction and retention/lifecycle are separate services.
    assert "app.jobs.reconstruction" in text
    assert "app.jobs.incident_lifecycle" in text or "app.jobs.retention" in text
    # PostgreSQL and Redis must not publish host ports in production.
    assert "5432:5432" not in text
    assert "6379:6379" not in text
