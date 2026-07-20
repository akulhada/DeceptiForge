# Purpose: performance regression guard — a large surface inventory stays bounded (no O(n^2)) and
#   recommendations remain capped.
from __future__ import annotations

import time
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import create_engine
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
        app_env="development", coverage_max_recommendations=25,
    )


def _session() -> Session:
    e = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(e)
    return sessionmaker(bind=e, expire_on_commit=False)()


def test_large_inventory_is_bounded() -> None:
    session = _session()
    org = uuid4()
    # 400 repository surfaces; half with a deployed decoy, half uncovered (a gap each).
    for i in range(400):
        repo = RepositoryRecord(
            organization_id=org, name=f"svc-{i}", root_path="/r", profile="{}", created_at=_NOW,
        )
        session.add(repo)
        session.flush()
        if i % 2 == 0:
            session.add(DecoyDeploymentRecord(
                organization_id=org, repository_id=repo.id, decoy_plan_id=uuid4(),
                validation_report_decision="accepted", status="deployed", target_branch="main",
                source_branch="df", base_commit_sha="a" * 40, monitoring_activated_at=_NOW,
                deployed_at=_NOW, created_at=_NOW,
            ))
    session.commit()

    started = time.perf_counter()
    result = engine.calculate(session, org, _settings(), now=_NOW)
    elapsed = time.perf_counter() - started

    assert len(result.surfaces) == 400
    # Recommendations are capped regardless of gap count.
    assert len(result.recommendations) <= 25
    # Loose bound: a linear pass over 400 surfaces must be well under a second on CI.
    assert elapsed < 3.0
    # Deterministic hash is stable across recomputation of identical state.
    assert engine.calculate(session, org, _settings(), now=_NOW).source_state_hash == \
        result.source_state_hash
