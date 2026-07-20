# Purpose: verify region fencing, scheduler leadership, epoch checks, maintenance mode, and the
#   degraded-mode readiness computation.
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config.settings import Settings
from app.database.base import Base
from app.services.reliability import degraded, fencing


def _settings(**over) -> Settings:  # type: ignore[no-untyped-def]
    base = dict(
        database_url="postgresql+psycopg://u:p@localhost/db",  # type: ignore[arg-type]
        app_env="development",
        evidence_encryption_mode="local",
        evidence_encryption_key="k" * 40,
    )
    base.update(over)
    return Settings(**base)  # type: ignore[arg-type]


def _session() -> Session:
    e = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(e)
    return sessionmaker(bind=e, expire_on_commit=False)()


def test_only_active_region_runs_side_effects() -> None:
    primary = _settings(cluster_role="primary")
    fencing.require_side_effects(primary)  # ok
    standby = _settings(cluster_role="standby")
    with pytest.raises(fencing.RegionFencedError):
        fencing.require_side_effects(standby)


def test_maintenance_mode_blocks_writes() -> None:
    with pytest.raises(fencing.RegionFencedError):
        fencing.require_writes(_settings(cluster_role="primary", maintenance_mode=True))


def test_scheduler_only_on_active_region() -> None:
    assert fencing.scheduler_allowed(_settings(cluster_role="primary")) is True
    assert fencing.scheduler_allowed(_settings(cluster_role="standby")) is False
    no_sched = _settings(cluster_role="primary", schedulers_enabled=False)
    assert fencing.scheduler_allowed(no_sched) is False


def test_stale_epoch_rejected() -> None:
    settings = _settings(active_region_epoch=5)
    fencing.check_epoch(settings, 5)  # current ok
    fencing.check_epoch(settings, 6)  # newer ok
    with pytest.raises(fencing.StaleEpochError):
        fencing.check_epoch(settings, 4)


def test_side_effects_disabled_flag() -> None:
    with pytest.raises(fencing.RegionFencedError):
        fencing.require_side_effects(
            _settings(cluster_role="primary", external_side_effects_enabled=False)
        )


def test_readiness_fails_without_mandatory_replay() -> None:
    session = _session()
    # Auth + signatures enforced but Redis (memory backend) is not the distributed replay store.
    settings = _settings(
        auth_enabled=True, monitor_signature_required=True, replay_backend="redis",
        redis_url="redis://unreachable:6379/0",
    )
    status = degraded.dependency_status(session, settings)
    # Encryption + db are fine; replay is required and unavailable -> not ready.
    assert status["encryption"]["status"] == "ok"  # type: ignore[index]
    assert degraded.is_ready(status) is False


def test_readiness_ok_when_replay_not_required() -> None:
    session = _session()
    settings = _settings(auth_enabled=False, monitor_signature_required=False)
    status = degraded.dependency_status(session, settings)
    assert degraded.is_ready(status) is True
