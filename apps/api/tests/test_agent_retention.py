# Purpose: verify agent activity retention removes only aged raw events, leaving recent events and
#   scope violations intact.
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import Engine, create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.base import Base
from app.models import records as _records  # noqa: F401
from app.models.records import AgentActivityEventRecord, ScopeViolationRecord
from app.repositories.artifacts import ArtifactRepository

_NOW = datetime.now(UTC)


def _engine() -> Engine:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    return engine


def _session(engine: Engine) -> Session:
    return sessionmaker(bind=engine, expire_on_commit=False)()


def _event(session: Session, org, sess_id, *, created_at) -> None:  # type: ignore[no-untyped-def]
    session.add(
        AgentActivityEventRecord(
            organization_id=org, sensor_id=uuid4(), session_id=sess_id,
            external_event_id=uuid4().hex, event_type="file_read", correlation_id="c",
            observed_at=created_at, created_at=created_at,
        )
    )


def test_purge_agent_events_removes_only_aged() -> None:
    engine = _engine()
    session = _session(engine)
    org = uuid4()
    sess_id = uuid4()
    _event(session, org, sess_id, created_at=_NOW - timedelta(days=45))  # aged
    _event(session, org, sess_id, created_at=_NOW - timedelta(days=1))   # recent
    # A violation must survive raw-event retention.
    session.add(
        ScopeViolationRecord(
            organization_id=org, session_id=sess_id, event_id=uuid4(),
            violation_type="sensitive_file_access", severity="medium", confidence=0.85,
            policy_rule="r", explanation="x", created_at=_NOW - timedelta(days=45),
        )
    )
    session.commit()

    repo = ArtifactRepository(session)
    removed = repo.purge_agent_activity_events(_NOW - timedelta(days=30))
    session.commit()

    assert removed == 1
    remaining = session.scalars(select(AgentActivityEventRecord)).all()
    assert len(remaining) == 1
    assert len(session.scalars(select(ScopeViolationRecord)).all()) == 1  # violation retained
