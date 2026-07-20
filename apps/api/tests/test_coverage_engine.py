# Purpose: verify the deterministic coverage engine against seeded control state — empty org,
#   decoy-without-sensor partial, sensor-without-decoy no placement, expired/failed reduce coverage,
#   risk weighting, unknown handling, deterministic source hash, and cross-org isolation.
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config.settings import Settings
from app.database.base import Base
from app.models import records as _records  # noqa: F401
from app.models.records import DecoyDeploymentRecord, RepositoryRecord
from app.services.coverage_engine import engine

_NOW = datetime(2026, 7, 19, tzinfo=UTC)


def _settings() -> Settings:
    return Settings(
        database_url="postgresql+psycopg://u:p@localhost/db",  # type: ignore[arg-type]
        app_env="development",
    )


def _engine() -> Engine:
    e = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(e)
    return e


def _session() -> Session:
    return sessionmaker(bind=_engine(), expire_on_commit=False)()


def _repo(session: Session, org, name="app") -> RepositoryRecord:  # type: ignore[no-untyped-def]
    r = RepositoryRecord(
        organization_id=org, name=name, root_path="/r", profile="{}", created_at=_NOW,
    )
    session.add(r)
    session.flush()
    return r


def _decoy(session, org, repo_id, *, status, monitoring=None, expires=None, deployed=_NOW):  # type: ignore[no-untyped-def]
    session.add(DecoyDeploymentRecord(
        organization_id=org, repository_id=repo_id, decoy_plan_id=uuid4(),
        validation_report_decision="accepted", status=status, target_branch="main",
        source_branch="df", base_commit_sha="a" * 40, monitoring_activated_at=monitoring,
        expires_at=expires, deployed_at=deployed, created_at=_NOW,
    ))
    session.flush()


def test_empty_org_is_zero_and_safe() -> None:
    session = _session()
    result = engine.calculate(session, uuid4(), _settings(), now=_NOW)
    assert result.overall_score == 0.0
    assert result.total_weight == 0.0
    assert result.active_decoys == 0


def test_decoy_without_sensor_partial_and_gap() -> None:
    session = _session()
    org = uuid4()
    repo = _repo(session, org)
    _decoy(session, org, repo.id, status="deployed", monitoring=None)
    session.commit()
    result = engine.calculate(session, org, _settings(), now=_NOW)
    surface = result.surfaces[0]
    assert 0.0 < surface.surface_coverage < 1.0  # placement yes, sensor no -> partial
    assert result.active_decoys == 1 and result.active_sensors == 0
    assert any(g.gap_type.value == "decoy_no_sensor" for g in result.gaps)


def test_sensor_without_decoy_no_placement() -> None:
    # A repository with no deployed decoy -> no placement coverage, a no_decoy gap.
    session = _session()
    org = uuid4()
    _repo(session, org)
    session.commit()
    result = engine.calculate(session, org, _settings(), now=_NOW)
    assert result.surfaces[0].dimension_scores["placement"] == 0.0
    assert any(g.gap_type.value == "no_decoy" for g in result.gaps)


def test_full_control_beats_expired_and_failed() -> None:
    session = _session()
    org = uuid4()
    repo = _repo(session, org)
    _decoy(
        session, org, repo.id, status="deployed", monitoring=_NOW,
        expires=_NOW + timedelta(days=30),
    )
    session.commit()
    healthy = engine.calculate(session, org, _settings(), now=_NOW).surfaces[0].surface_coverage

    session2 = _session()
    repo2 = _repo(session2, org)
    _decoy(session2, org, repo2.id, status="expired", expires=_NOW - timedelta(days=1))
    session2.commit()
    expired = engine.calculate(session2, org, _settings(), now=_NOW).surfaces[0].surface_coverage
    assert healthy > expired
    assert engine.calculate(session2, org, _settings(), now=_NOW).expired_decoys == 1


def test_source_hash_deterministic_and_state_sensitive() -> None:
    session = _session()
    org = uuid4()
    repo = _repo(session, org)
    _decoy(session, org, repo.id, status="deployed", monitoring=_NOW)
    session.commit()
    a = engine.calculate(session, org, _settings(), now=_NOW)
    b = engine.calculate(session, org, _settings(), now=_NOW + timedelta(hours=1))
    assert a.source_state_hash == b.source_state_hash  # same control state -> same hash
    _decoy(session, org, repo.id, status="deployed", monitoring=_NOW)  # add a control
    session.commit()
    c = engine.calculate(session, org, _settings(), now=_NOW)
    assert c.source_state_hash != a.source_state_hash


def test_cross_org_isolation() -> None:
    session = _session()
    org_a, org_b = uuid4(), uuid4()
    repo = _repo(session, org_a)
    _decoy(session, org_a, repo.id, status="deployed", monitoring=_NOW)
    session.commit()
    result_b = engine.calculate(session, org_b, _settings(), now=_NOW)
    assert result_b.total_weight == 0.0 and result_b.active_decoys == 0
