# Purpose: verify integration retention removes only aged delivered/dead-lettered delivery payloads
#   while dead-letter hash records are retained longer.
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.base import Base
from app.models import records as _records  # noqa: F401
from app.models.records import IntegrationDeadLetterRecord, IntegrationDeliveryRecord
from app.repositories.artifacts import ArtifactRepository

_NOW = datetime.now(UTC)


def _session() -> Session:
    e = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(e)
    return sessionmaker(bind=e, expire_on_commit=False)()


def _delivery(session, org, *, status, created_at) -> None:  # type: ignore[no-untyped-def]
    session.add(
        IntegrationDeliveryRecord(
            organization_id=org,
            integration_id=uuid4(),
            source_type="alert",
            source_id="a",
            event_type="deceptiforge.alert.created",
            idempotency_key=uuid4().hex,
            status=status,
            envelope_data="{}",
            payload_hash="h",
            created_at=created_at,
        )
    )


def test_retention_removes_aged_delivered_only() -> None:
    session = _session()
    org = uuid4()
    _delivery(session, org, status="delivered", created_at=_NOW - timedelta(days=30))  # aged
    _delivery(session, org, status="delivered", created_at=_NOW - timedelta(days=1))  # recent
    _delivery(session, org, status="queued", created_at=_NOW - timedelta(days=30))  # not terminal
    session.commit()

    repo = ArtifactRepository(session)
    removed = repo.purge_integration_deliveries(_NOW - timedelta(days=14))
    session.commit()
    assert removed == 1
    remaining = session.scalars(select(IntegrationDeliveryRecord)).all()
    assert len(remaining) == 2  # recent delivered + queued survive


def test_dead_letters_retained_longer() -> None:
    session = _session()
    org = uuid4()
    session.add(
        IntegrationDeadLetterRecord(
            organization_id=org,
            integration_id=uuid4(),
            delivery_id=uuid4(),
            reason_code="permanent",
            first_failed_at=_NOW - timedelta(days=30),
            final_failed_at=_NOW - timedelta(days=30),
            attempt_count=6,
            payload_hash="h",
            created_at=_NOW - timedelta(days=30),
        )
    )
    session.commit()
    repo = ArtifactRepository(session)
    # A 14-day delivery cutoff never touches dead letters (they use a 90-day cutoff).
    assert repo.purge_integration_dead_letters(_NOW - timedelta(days=90)) == 0
    assert len(session.scalars(select(IntegrationDeadLetterRecord)).all()) == 1
