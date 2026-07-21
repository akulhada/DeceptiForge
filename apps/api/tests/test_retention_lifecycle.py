# Purpose: verify scheduled retention and incident-lifecycle jobs.
# Responsibilities: confirm retention deletes only aged rows (leaving newer ones and not corrupting
#   other organizations), narrative revisions prune to the configured count, stale incidents are
#   retired only when eligible, resolved/stale incidents archive past the window, and the job
#   entrypoints run idempotently under a sqlite-backed session. Dependencies: repository, records.
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import Engine, create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config.settings import Settings
from app.database.base import Base
from app.models import records as _records  # noqa: F401
from app.models.domain.operations import AlertEvidence, MonitorType, NormalizedAlert, Severity
from app.models.records import (
    DetectionEventRecord,
    IncidentRecord,
    NarrativeRevisionRecord,
)
from app.repositories.artifacts import ArtifactRepository
from app.services.incident_reconstruction import IncidentReconstructionEngine

_NOW = datetime.now(UTC)


def _engine() -> Engine:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    return engine


def _session(engine: Engine) -> Session:
    return sessionmaker(bind=engine, expire_on_commit=False)()


# ---- retention -----------------------------------------------------------------------------------


def test_purge_detection_events_removes_only_aged_rows() -> None:
    session = _session(_engine())
    org = uuid4()
    old = DetectionEventRecord(
        id=uuid4(),
        organization_id=org,
        trace_identifier="t",
        decoy_id=uuid4(),
        data="{}",
        created_at=_NOW - timedelta(days=40),
    )
    fresh = DetectionEventRecord(
        id=uuid4(),
        organization_id=org,
        trace_identifier="t",
        decoy_id=uuid4(),
        data="{}",
        created_at=_NOW - timedelta(days=1),
    )
    session.add_all([old, fresh])
    session.commit()

    removed = ArtifactRepository(session).purge_detection_events(_NOW - timedelta(days=30))
    session.commit()

    remaining = session.scalars(select(DetectionEventRecord.id)).all()
    assert removed == 1
    assert remaining == [fresh.id]


def test_purge_is_idempotent() -> None:
    session = _session(_engine())
    session.add(
        DetectionEventRecord(
            id=uuid4(),
            organization_id=uuid4(),
            trace_identifier="t",
            decoy_id=uuid4(),
            data="{}",
            created_at=_NOW - timedelta(days=40),
        )
    )
    session.commit()
    repo = ArtifactRepository(session)
    assert repo.purge_detection_events(_NOW - timedelta(days=30)) == 1
    session.commit()
    assert repo.purge_detection_events(_NOW - timedelta(days=30)) == 0  # nothing left to remove


def test_prune_narrative_revisions_keeps_newest_per_incident() -> None:
    session = _session(_engine())
    org, incident = uuid4(), uuid4()
    other_incident = uuid4()
    for revision in range(1, 6):
        session.add(
            NarrativeRevisionRecord(
                organization_id=org,
                incident_id=incident,
                revision_number=revision,
                context_hash="h",
                status="ok",
                data="{}",
            )
        )
    session.add(
        NarrativeRevisionRecord(
            organization_id=org,
            incident_id=other_incident,
            revision_number=1,
            context_hash="h",
            status="ok",
            data="{}",
        )
    )
    session.commit()

    pruned = ArtifactRepository(session).prune_all_narrative_revisions(keep=2)
    session.commit()

    kept = session.scalars(
        select(NarrativeRevisionRecord.revision_number).where(
            NarrativeRevisionRecord.incident_id == incident
        )
    ).all()
    assert pruned == 3
    assert sorted(kept) == [4, 5]  # newest two retained
    # The unrelated incident's single revision is untouched.
    assert (
        len(
            session.scalars(
                select(NarrativeRevisionRecord).where(
                    NarrativeRevisionRecord.incident_id == other_incident
                )
            ).all()
        )
        == 1
    )


# ---- incident lifecycle --------------------------------------------------------------------------


def _incident_alert(trace: str, at: datetime) -> NormalizedAlert:
    return NormalizedAlert(
        alert_id=uuid4(),
        trace_identifier=trace,
        decoy_id=uuid4(),
        severity=Severity.HIGH,
        title="t",
        summary="observed",
        source_monitor=MonitorType.REPOSITORY,
        confidence=0.9,
        first_seen=at,
        last_seen=at,
        event_count=1,
        deduplication_key=f"{trace}:id:repository:path:repository:content_access",
        affected_placement_id=uuid4(),
        affected_decoy_type="secret",
        evidence=(AlertEvidence(excerpt=trace, digest="a" * 64, location="src/x.py"),),
        raw_event_ids=(uuid4(),),
        recommended_actions=("review",),
        correlation_id=uuid4(),
    )


def test_retire_stale_incidents_marks_only_eligible() -> None:
    session = _session(_engine())
    repo = ArtifactRepository(session)
    org = uuid4()
    engine = IncidentReconstructionEngine()
    stale = engine.reconstruct(
        (_incident_alert("OLD", _NOW - timedelta(days=3)),), organization_id=org
    )
    fresh = engine.reconstruct((_incident_alert("NEW", _NOW),), organization_id=org)
    repo.upsert_incidents_for_organization(org, stale + fresh)
    session.commit()

    retired = repo.retire_all_stale_incidents(_NOW, 86_400)  # stale after 1 day
    session.commit()

    statuses = {row.status for row in session.scalars(select(IncidentRecord)).all()}
    assert retired == 1
    assert "stale" in statuses and "open" in statuses


def test_archive_incidents_removes_only_resolved_or_stale_past_window() -> None:
    session = _session(_engine())
    org = uuid4()
    keep_open = IncidentRecord(
        id=uuid4(),
        organization_id=org,
        status="open",
        last_seen=_NOW - timedelta(days=60),
        data="{}",
    )
    archive_stale = IncidentRecord(
        id=uuid4(),
        organization_id=org,
        status="stale",
        last_seen=_NOW - timedelta(days=60),
        data="{}",
    )
    recent_stale = IncidentRecord(
        id=uuid4(),
        organization_id=org,
        status="stale",
        last_seen=_NOW - timedelta(days=1),
        data="{}",
    )
    session.add_all([keep_open, archive_stale, recent_stale])
    session.commit()

    removed = ArtifactRepository(session).archive_incidents(_NOW - timedelta(days=30))
    session.commit()

    remaining = set(session.scalars(select(IncidentRecord.id)).all())
    assert removed == 1
    assert remaining == {keep_open.id, recent_stale.id}


# ---- job entrypoints -----------------------------------------------------------------------------


def _prod_settings() -> Settings:
    return Settings(
        database_url="postgresql+psycopg://u:p@localhost/db",  # type: ignore[arg-type]
        app_env="development",
    )


def test_retention_job_runs_end_to_end(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    engine = _engine()
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    seed = factory()
    seed.add(
        DetectionEventRecord(
            id=uuid4(),
            organization_id=uuid4(),
            trace_identifier="t",
            decoy_id=uuid4(),
            data="{}",
            created_at=_NOW - timedelta(days=40),
        )
    )
    seed.commit()
    seed.close()

    monkeypatch.setattr("app.jobs._runtime.get_sessionmaker", lambda: factory)
    from app.jobs import retention

    results = retention.run(_prod_settings())
    assert results["monitoring_events"] == 1


def test_incident_lifecycle_job_runs_end_to_end(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    engine = _engine()
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    org = uuid4()
    seed = factory()
    ArtifactRepository(seed).upsert_incidents_for_organization(
        org,
        IncidentReconstructionEngine().reconstruct(
            (_incident_alert("OLD", _NOW - timedelta(days=3)),), organization_id=org
        ),
    )
    seed.commit()
    seed.close()

    monkeypatch.setattr("app.jobs._runtime.get_sessionmaker", lambda: factory)
    from app.jobs import incident_lifecycle

    results = incident_lifecycle.run(_prod_settings())
    assert results["retired"] == 1
