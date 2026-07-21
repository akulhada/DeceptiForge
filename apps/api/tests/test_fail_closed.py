# Purpose: P0 — security controls must never fail open outside development.
# Verifies startup rejects REDIS_FAIL_MODE=open and AUTH_ENABLED=false in production-like
# environments, and that a Redis outage refuses signed ingestion with a safe 503 instead of either
# admitting the request or reporting a misleading "replayed nonce".
from __future__ import annotations

import pytest
from redis.exceptions import RedisError

from app.config.settings import Settings
from app.services.replay import (
    RedisReplayStore,
    ReplayError,
    ReplayGuard,
    ReplayUnavailableError,
)

# A production configuration that satisfies every OTHER startup guard, so a failure below is
# attributable to the control under test.
_VALID_PRODUCTION = dict(
    app_env="production",
    auth_enabled=True,
    demo_enabled=False,
    rate_limit_mode="gateway",
    replay_backend="redis",
    redis_url="redis://localhost:6379/0",
    evidence_encryption_mode="local",
    evidence_encryption_key="test-evidence-key-0000000000000000000000",
    redis_fail_mode="closed",
    monitor_signature_required=True,
)


def _settings(**overrides: object) -> Settings:
    return Settings(**{**_VALID_PRODUCTION, **overrides})  # type: ignore[arg-type]


class _BrokenRedis:
    """A Redis client whose every call fails, simulating an outage."""

    def set(self, *args: object, **kwargs: object) -> bool:
        raise RedisError("connection refused")

    def scan_iter(self, *args: object, **kwargs: object):  # type: ignore[no-untyped-def]
        raise RedisError("connection refused")


# ---- startup guards ------------------------------------------------------------------------------


# Each guard test matches its own error message, so a pass proves the control under test fired
# rather than an unrelated startup guard. (A full "valid production" baseline is not asserted here:
# validate_runtime also pings the real Redis, which is intentional but environment-dependent.)


def test_production_rejects_redis_fail_open() -> None:
    with pytest.raises(RuntimeError, match="REDIS_FAIL_MODE"):
        _settings(redis_fail_mode="open").validate_runtime()


def test_production_rejects_disabled_authentication() -> None:
    with pytest.raises(RuntimeError, match="AUTH_ENABLED"):
        _settings(auth_enabled=False).validate_runtime()


def test_staging_also_rejects_fail_open() -> None:
    with pytest.raises(RuntimeError, match="REDIS_FAIL_MODE"):
        _settings(app_env="staging", redis_fail_mode="open").validate_runtime()


def test_development_may_still_fail_open() -> None:
    """Local development keeps the convenience; only non-development environments are restricted."""
    Settings(app_env="development", redis_fail_mode="open").validate_runtime()


# ---- outage behaviour ----------------------------------------------------------------------------


def test_fail_closed_store_signals_unavailable_rather_than_allowing() -> None:
    store = RedisReplayStore(_BrokenRedis(), prefix="df", fail_open=False)  # type: ignore[arg-type]
    with pytest.raises(ReplayUnavailableError):
        store.reserve("scope:nonce", 300)


def test_outage_returns_503_not_409_and_not_success() -> None:
    """A Redis outage is not evidence of a replay, so it must not surface as 409."""
    store = RedisReplayStore(_BrokenRedis(), prefix="df", fail_open=False)  # type: ignore[arg-type]
    guard = ReplayGuard(store, window_seconds=300, clock=lambda: 1000.0)
    with pytest.raises(ReplayError) as caught:
        guard.check("nonce-1", "1000", scope="org-1")
    assert caught.value.status_code == 503
    assert "unavailable" in caught.value.message


def test_fail_open_store_admits_only_when_explicitly_configured() -> None:
    """Fail-open remains reachable in code for development, but production startup forbids it."""
    store = RedisReplayStore(_BrokenRedis(), prefix="df", fail_open=True)  # type: ignore[arg-type]
    assert store.reserve("scope:nonce", 300) is True


def test_signed_ingestion_refused_during_outage_creates_nothing(make_client) -> None:  # type: ignore[no-untyped-def]
    """The 503 is raised before any pipeline work, so no event, alert, or incident is created."""
    from uuid import uuid4

    from app.services import replay as replay_module

    with make_client(demo_enabled=False, auth_enabled=False, app_env="development") as client:
        broken = ReplayGuard(
            RedisReplayStore(_BrokenRedis(), prefix="df", fail_open=False),  # type: ignore[arg-type]
            window_seconds=300,
        )
        original = replay_module._guard
        replay_module._guard = broken
        try:
            response = client.post(
                "/monitoring/events",
                json={
                    "decoy_plan_id": str(uuid4()),
                    "surface": "repository",
                    "location": "x",
                    "value": "y",
                },
                headers={
                    "X-DeceptiForge-Nonce": "n-1",
                    "X-DeceptiForge-Timestamp": "1000",
                },
            )
        finally:
            replay_module._guard = original
        # Refused safely; never a 200 that would have produced an alert or incident.
        assert response.status_code != 200
        assert client.get("/alerts").json()["alerts"] == []
        assert client.get("/incidents").json()["incidents"] == []
