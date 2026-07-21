# Purpose: verify atomic alert upsert and concurrent duplicate-ingestion correctness.
# Responsibilities: prove sequential upserts merge one episode (event_count/first_seen/last_seen),
#   retries are idempotent, distinct episodes and organizations stay separate, and — against a live
#   PostgreSQL (POSTGRES_TEST_URL, provided by CI) — many concurrent duplicate ingests produce one
#   alert with the correct event_count and no client-visible unique violation. Dependencies:
#   repository, alerting engine, records.
from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import Engine, create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.base import Base
from app.models import records as _records  # noqa: F401
from app.models.domain.operations import (
    DetectionMethod,
    DetectionSource,
    MonitorType,
    RawDetectionEvent,
    Severity,
)
from app.models.records import AlertRecord
from app.repositories.artifacts import ArtifactRepository
from app.services.alerting import AlertingPipeline
from app.services.encryption import NoopEncryptionProvider

_WINDOW = datetime(2026, 1, 1, tzinfo=UTC)


def _sqlite_engine() -> Engine:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    return engine


def _event(*, at: datetime, trace: str = "DFG-A", decoy=None, event_id=None) -> RawDetectionEvent:
    return RawDetectionEvent(
        event_id=event_id or uuid4(),
        trace_identifier=trace,
        decoy_id=decoy or uuid4(),
        monitor_type=MonitorType.REPOSITORY,
        source=DetectionSource.REPOSITORY,
        detection_method=DetectionMethod.CONTENT_ACCESS,
        observed_location="src/x.py",
        observed_value_excerpt=f"copied {trace}",
        evidence_digest="a" * 64,
        confidence=0.9,
        severity_suggestion=Severity.HIGH,
        timestamp=at,
        correlation_id=uuid4(),
    )


def _candidate(org, event: RawDetectionEvent):  # type: ignore[no-untyped-def]
    return AlertingPipeline().ingest(event, None, organization_id=org)


def _repo(session: Session) -> ArtifactRepository:
    # Noop encryption keeps the stored blob inspectable and avoids key setup in unit tests.
    return ArtifactRepository(session, encryption=NoopEncryptionProvider())


# ---- sequential upsert semantics -----------------------------------------------------------------


def test_upsert_merges_same_episode_into_one_alert() -> None:
    session = sessionmaker(bind=_sqlite_engine(), expire_on_commit=False)()
    repo = _repo(session)
    org, decoy = uuid4(), uuid4()
    first = _candidate(org, _event(at=_WINDOW, decoy=decoy))
    second = _candidate(org, _event(at=_WINDOW + timedelta(seconds=30), decoy=decoy))
    assert first is not None and second is not None
    assert first.alert_id == second.alert_id  # same episode identity

    repo.upsert_alert_atomic(org, first)
    session.commit()
    merged = repo.upsert_alert_atomic(org, second)
    session.commit()

    rows = session.scalars(select(AlertRecord)).all()
    assert len(rows) == 1
    assert merged.event_count == 2
    assert merged.first_seen == _WINDOW
    assert merged.last_seen == _WINDOW + timedelta(seconds=30)
    assert rows[0].event_count == 2


def test_upsert_counts_each_accepted_event_without_extra_rows() -> None:
    # Each accepted ingest increments the one episode row (no lost update, no extra rows). Genuine
    # duplicate delivery is stopped upstream by the nonce replay guard, not by this merge.
    session = sessionmaker(bind=_sqlite_engine(), expire_on_commit=False)()
    repo = _repo(session)
    org, decoy = uuid4(), uuid4()
    for _ in range(5):
        candidate = _candidate(org, _event(at=_WINDOW, decoy=decoy))
        assert candidate is not None
        repo.upsert_alert_atomic(org, candidate)
        session.commit()
    rows = session.scalars(select(AlertRecord)).all()
    assert len(rows) == 1
    assert rows[0].event_count == 5


def test_later_episode_stays_a_distinct_alert() -> None:
    session = sessionmaker(bind=_sqlite_engine(), expire_on_commit=False)()
    repo = _repo(session)
    org, decoy = uuid4(), uuid4()
    early = _candidate(org, _event(at=_WINDOW, decoy=decoy))
    later = _candidate(org, _event(at=_WINDOW + timedelta(hours=2), decoy=decoy))
    assert early is not None and later is not None
    assert early.alert_id != later.alert_id  # separate time bucket -> separate episode
    repo.upsert_alert_atomic(org, early)
    repo.upsert_alert_atomic(org, later)
    session.commit()
    assert len(session.scalars(select(AlertRecord)).all()) == 2


def test_same_episode_different_orgs_do_not_collide() -> None:
    session = sessionmaker(bind=_sqlite_engine(), expire_on_commit=False)()
    repo = _repo(session)
    org_a, org_b, decoy = uuid4(), uuid4(), uuid4()
    a = _candidate(org_a, _event(at=_WINDOW, decoy=decoy))
    b = _candidate(org_b, _event(at=_WINDOW, decoy=decoy))
    assert a is not None and b is not None
    assert a.alert_id != b.alert_id  # organization folded into the identity
    repo.upsert_alert_atomic(org_a, a)
    repo.upsert_alert_atomic(org_b, b)
    session.commit()
    assert len(session.scalars(select(AlertRecord)).all()) == 2


# ---- live PostgreSQL concurrency (CI: POSTGRES_TEST_URL) --------------------------------


def _postgres_url() -> str | None:
    return os.environ.get("POSTGRES_TEST_URL")


@pytest.mark.skipif(_postgres_url() is None, reason="POSTGRES_TEST_URL not set")
def test_postgres_integration_concurrent_duplicates_make_one_alert() -> None:
    url = _postgres_url()
    assert url is not None
    engine = create_engine(url, pool_size=40, max_overflow=10)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    org, decoy = uuid4(), uuid4()
    # 50 distinct events in the same episode window (same trace/decoy/location => same alert_id).
    events = [_event(at=_WINDOW + timedelta(seconds=i % 60), decoy=decoy) for i in range(50)]

    def ingest(event: RawDetectionEvent) -> None:
        session = factory()
        try:
            candidate = AlertingPipeline().ingest(event, None, organization_id=org)
            assert candidate is not None
            ArtifactRepository(session, encryption=NoopEncryptionProvider()).upsert_alert_atomic(
                org, candidate
            )
            session.commit()
        finally:
            session.close()

    with ThreadPoolExecutor(max_workers=32) as pool:
        list(pool.map(ingest, events))

    check = factory()
    try:
        rows = check.scalars(select(AlertRecord).where(AlertRecord.organization_id == org)).all()
        assert len(rows) == 1  # exactly one alert despite concurrent duplicates
        assert rows[0].event_count == len(events)  # every event counted, none lost
    finally:
        check.close()
        engine.dispose()
