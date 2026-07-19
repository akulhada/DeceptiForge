# Purpose: define the SQLAlchemy persistence records for the API vertical slice.
# Responsibilities: store each engine artifact as a queryable row plus a JSON blob of the
#   immutable domain model, keeping database representation separate from the domain contract.
# Dependencies: the declarative Base only; domain models are serialized to/from the blob column.
from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.config.constants import DEMO_ORGANIZATION_ID
from app.database.base import Base


def _now() -> datetime:
    return datetime.now(UTC)


class RepositoryRecord(Base):
    __tablename__ = "repositories"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid, index=True, default=DEMO_ORGANIZATION_ID)
    name: Mapped[str] = mapped_column(String(256))
    root_path: Mapped[str] = mapped_column(String(2048))
    profile: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class ContextProfileRecord(Base):
    __tablename__ = "context_profiles"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid, index=True, default=DEMO_ORGANIZATION_ID)
    repository_id: Mapped[UUID] = mapped_column(ForeignKey("repositories.id"), index=True)
    data: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class PlacementPlanRecord(Base):
    __tablename__ = "placement_plans"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid, index=True, default=DEMO_ORGANIZATION_ID)
    repository_id: Mapped[UUID] = mapped_column(ForeignKey("repositories.id"), index=True)
    data: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class DecoyPlanRecord(Base):
    __tablename__ = "decoy_plans"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid, index=True, default=DEMO_ORGANIZATION_ID)
    repository_id: Mapped[UUID] = mapped_column(ForeignKey("repositories.id"), index=True)
    data: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class ValidationReportRecord(Base):
    __tablename__ = "validation_reports"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid, index=True, default=DEMO_ORGANIZATION_ID)
    decoy_plan_id: Mapped[UUID] = mapped_column(ForeignKey("decoy_plans.id"), index=True)
    decoy_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    data: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class DetectionEventRecord(Base):
    __tablename__ = "detection_events"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(Uuid, index=True, default=DEMO_ORGANIZATION_ID)
    trace_identifier: Mapped[str] = mapped_column(String(128), index=True)
    decoy_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    data: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class AlertRecord(Base):
    __tablename__ = "alerts"
    __table_args__ = (
        # One row per (organization, detection surface, time bucket) = one alert episode. A later
        # episode on the same surface uses a new bucket, so legitimate re-detections stay distinct.
        UniqueConstraint(
            "organization_id",
            "deduplication_key",
            "episode_bucket",
            name="uq_alert_episode",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(Uuid, index=True, default=DEMO_ORGANIZATION_ID)
    trace_identifier: Mapped[str] = mapped_column(String(128), index=True)
    decoy_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    event_count: Mapped[int] = mapped_column(Integer, default=1)
    episode_bucket: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    # Strong correlation keys promoted to indexed columns so reconstruction can find related alerts
    # without scanning the whole table.
    affected_placement_id: Mapped[UUID | None] = mapped_column(Uuid, index=True, nullable=True)
    correlation_id: Mapped[UUID | None] = mapped_column(Uuid, index=True, nullable=True)
    deduplication_key: Mapped[str | None] = mapped_column(String(512), index=True, nullable=True)
    first_seen: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True, nullable=True
    )
    last_seen: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True, nullable=True
    )
    data: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class ReconstructionJobRecord(Base):
    """A unit of incident-reconstruction work enqueued by monitoring ingestion.

    Ingestion persists the event, upserts the alert, and appends one of these rows, then returns.
    A separate worker claims pending rows and reconstructs only the incidents touched by the
    triggering alert's strong correlation keys.
    """

    __tablename__ = "reconstruction_jobs"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    status: Mapped[str] = mapped_column(String(16), index=True, default="pending")
    trace_identifier: Mapped[str] = mapped_column(String(128))
    decoy_id: Mapped[UUID] = mapped_column(Uuid)
    affected_placement_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    correlation_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, default=_now)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class IncidentRecord(Base):
    __tablename__ = "incidents"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(Uuid, index=True, default=DEMO_ORGANIZATION_ID)
    # Lifecycle status and last-activity promoted to indexed columns for lifecycle/retention jobs.
    status: Mapped[str | None] = mapped_column(String(16), index=True, nullable=True)
    last_seen: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True, nullable=True
    )
    data: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class ApiKeyRecord(Base):
    """A hashed, organization-bound API key. The plaintext is never stored."""

    __tablename__ = "api_keys"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    key_prefix: Mapped[str] = mapped_column(String(16), index=True)
    key_hash: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(128))
    role: Mapped[str] = mapped_column(String(32))
    scopes: Mapped[str] = mapped_column(Text)  # JSON array of permission strings
    status: Mapped[str] = mapped_column(String(16), default="active")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class SecurityAuditRecord(Base):
    """Append-only security audit event. Never stores secrets or raw payloads."""

    __tablename__ = "security_audit"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID | None] = mapped_column(Uuid, index=True, nullable=True)
    action: Mapped[str] = mapped_column(String(64), index=True)
    outcome: Mapped[str] = mapped_column(String(16))
    request_id: Mapped[str] = mapped_column(String(64))
    detail: Mapped[str] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class MonitorCredentialRecord(Base):
    """A monitor signing credential. The signing secret is stored encrypted, never in plaintext."""

    __tablename__ = "monitor_credentials"
    __table_args__ = (
        UniqueConstraint("monitor_id", name="uq_monitor_credential_monitor_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    monitor_id: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(128))
    # Encrypted signing secret plus the key version used, so keys can be rotated.
    secret_ciphertext: Mapped[str] = mapped_column(Text)
    secret_key_version: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16), default="active")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class NarrativeRevisionRecord(Base):
    """One immutable narrative generation. Regeneration appends a revision, never overwrites."""

    __tablename__ = "narrative_revisions"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "incident_id",
            "revision_number",
            name="uq_narrative_revision_scope",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid, index=True, default=DEMO_ORGANIZATION_ID)
    incident_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    revision_number: Mapped[int] = mapped_column(Integer)
    context_hash: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32))
    data: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
