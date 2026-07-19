# Purpose: verify asynchronous, indexed incident reconstruction.
# Responsibilities: confirm ingestion enqueues work without reconstructing synchronously, the worker
#   reconstructs only the affected incident via an indexed related-alert lookup, jobs are claimed
#   exactly once under concurrent workers, related lookups stay organization-scoped, and reprocess
#   is idempotent (deterministic incident identity). Dependencies: repository, worker, records.
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.base import Base
from app.models import records as _records  # noqa: F401  (register tables)
from app.models.domain.operations import AlertEvidence, MonitorType, NormalizedAlert, Severity
from app.repositories.artifacts import ArtifactRepository
from app.services.incident_reconstruction import ReconstructionWorker


def _engine() -> Engine:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    return engine


def _session(engine: Engine) -> Session:
    return sessionmaker(bind=engine, expire_on_commit=False)()


def _alert(
    trace: str,
    at: datetime,
    *,
    decoy_id=None,
    monitor: MonitorType = MonitorType.REPOSITORY,
) -> NormalizedAlert:
    return NormalizedAlert(
        alert_id=uuid4(),
        trace_identifier=trace,
        decoy_id=decoy_id or uuid4(),
        severity=Severity.HIGH,
        title="t",
        summary="observed",
        source_monitor=monitor,
        confidence=0.9,
        first_seen=at,
        last_seen=at,
        event_count=1,
        deduplication_key=f"{trace}:id:{monitor.value}:path:repository:content_access",
        affected_placement_id=uuid4(),
        affected_decoy_type="secret",
        evidence=(AlertEvidence(excerpt=trace, digest="a" * 64, location="src/x.py"),),
        raw_event_ids=(uuid4(),),
        recommended_actions=("review",),
        correlation_id=uuid4(),
    )


def test_enqueue_does_not_reconstruct_synchronously() -> None:
    engine = _engine()
    session = _session(engine)
    repo = ArtifactRepository(session)
    org = uuid4()
    alert = _alert("DFG-A", datetime.now(UTC))
    repo.add_alert(org, alert)
    repo.enqueue_reconstruction(org, alert, 3600)
    session.commit()

    assert repo.pending_reconstruction_count(org) == 1
    assert repo.incidents_for_organization(org) == ()  # no incident until a worker runs


def test_worker_reconstructs_only_affected_incident() -> None:
    engine = _engine()
    session = _session(engine)
    repo = ArtifactRepository(session)
    org = uuid4()
    now = datetime.now(UTC)
    trigger = _alert("DFG-A", now)
    repo.add_alert(org, trigger)
    repo.enqueue_reconstruction(org, trigger, 3600)
    # An unrelated alert exists but is not enqueued; it must not be pulled into this incident.
    repo.add_alert(org, _alert("DFG-Z", now))
    session.commit()

    processed = ReconstructionWorker(repo).drain(org)
    session.commit()

    assert processed == 1
    incidents = repo.incidents_for_organization(org)
    assert len(incidents) == 1
    assert trigger.alert_id in incidents[0].involved_alert_ids
    assert "DFG-Z" not in incidents[0].involved_trace_ids
    assert repo.pending_reconstruction_count(org) == 0


def test_related_lookup_is_organization_scoped() -> None:
    engine = _engine()
    session = _session(engine)
    repo = ArtifactRepository(session)
    org_a, org_b = uuid4(), uuid4()
    now = datetime.now(UTC)
    shared = _alert("DFG-SHARED", now)
    other = _alert("DFG-SHARED", now, decoy_id=shared.decoy_id)  # same trace, different org
    repo.add_alert(org_a, shared)
    repo.add_alert(org_b, other)
    session.commit()

    related = repo.related_alerts(
        org_a,
        trace_identifier="DFG-SHARED",
        decoy_id=shared.decoy_id,
        affected_placement_id=None,
        correlation_id=None,
        window_start=now - timedelta(hours=1),
        window_end=now + timedelta(hours=1),
    )
    assert {a.alert_id for a in related} == {shared.alert_id}  # org B's alert never appears


def test_job_claimed_exactly_once_under_concurrent_workers() -> None:
    engine = _engine()  # shared engine models two workers against one database
    org = uuid4()
    seed = _session(engine)
    trigger = _alert("DFG-A", datetime.now(UTC))
    seed_repo = ArtifactRepository(seed)
    seed_repo.add_alert(org, trigger)
    seed_repo.enqueue_reconstruction(org, trigger, 3600)
    seed.commit()

    worker_a = ArtifactRepository(_session(engine))
    worker_b = ArtifactRepository(_session(engine))
    claimed_a = worker_a.claim_reconstruction_jobs(10, org)
    claimed_b = worker_b.claim_reconstruction_jobs(10, org)
    assert len(claimed_a) + len(claimed_b) == 1  # exactly one worker owns the job


def test_reprocessing_is_idempotent() -> None:
    engine = _engine()
    session = _session(engine)
    repo = ArtifactRepository(session)
    org = uuid4()
    trigger = _alert("DFG-A", datetime.now(UTC))
    repo.add_alert(org, trigger)
    repo.enqueue_reconstruction(org, trigger, 3600)
    session.commit()
    ReconstructionWorker(repo).drain(org)
    session.commit()
    first = repo.incidents_for_organization(org)

    # Enqueue and reprocess the same alert: deterministic identity means the incident is upserted.
    repo.enqueue_reconstruction(org, trigger, 3600)
    session.commit()
    ReconstructionWorker(repo).drain(org)
    session.commit()
    second = repo.incidents_for_organization(org)

    assert len(second) == 1
    assert first[0].incident_id == second[0].incident_id
