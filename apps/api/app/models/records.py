# Purpose: define the SQLAlchemy persistence records for the API vertical slice.
# Responsibilities: store each engine artifact as a queryable row plus a JSON blob of the
#   immutable domain model, keeping database representation separate from the domain contract.
# Dependencies: the declarative Base only; domain models are serialized to/from the blob column.
from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, Uuid
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

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(Uuid, index=True, default=DEMO_ORGANIZATION_ID)
    trace_identifier: Mapped[str] = mapped_column(String(128), index=True)
    decoy_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    data: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class IncidentRecord(Base):
    __tablename__ = "incidents"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(Uuid, index=True, default=DEMO_ORGANIZATION_ID)
    data: Mapped[str] = mapped_column(Text)
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
