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


class DecoyDeploymentRecord(Base):
    """A reviewable, reversible decoy deployment through a controlled branch + pull request."""

    __tablename__ = "decoy_deployments"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    repository_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    scan_job_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    decoy_plan_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    validation_report_decision: Mapped[str] = mapped_column(String(16))
    requested_by_actor_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    approved_by_actor_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    status: Mapped[str] = mapped_column(String(32), index=True)
    target_branch: Mapped[str] = mapped_column(String(255))
    source_branch: Mapped[str] = mapped_column(String(255))
    pull_request_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pull_request_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    base_commit_sha: Mapped[str] = mapped_column(String(64))
    deployed_commit_sha: Mapped[str | None] = mapped_column(String(64), nullable=True)
    preview_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Serialized DeploymentPreview (rendered change-set; inert content only, no real secrets).
    preview_data: Mapped[str | None] = mapped_column(Text, nullable=True)
    monitoring_activated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deployed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    safe_failure_message: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class DecoyDeploymentItemRecord(Base):
    """One file change owned by a deployment. Hashes let retire/rollback touch only its content."""

    __tablename__ = "decoy_deployment_items"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    deployment_id: Mapped[UUID] = mapped_column(
        ForeignKey("decoy_deployments.id"), index=True
    )
    decoy_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    target_path: Mapped[str] = mapped_column(String(2048))
    operation: Mapped[str] = mapped_column(String(16))
    trace_identifier: Mapped[str] = mapped_column(String(128), index=True)
    original_content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    proposed_content_hash: Mapped[str] = mapped_column(String(64))
    deployed_content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Serialized rendered content + deployment marker (inert; synthetic values only).
    content_data: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="planned")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class DeploymentApprovalRecord(Base):
    """An approve/reject decision. Separation-of-duties is enforced against requested_by."""

    __tablename__ = "deployment_approvals"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    deployment_id: Mapped[UUID] = mapped_column(
        ForeignKey("decoy_deployments.id"), index=True
    )
    organization_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    actor_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    decision: Mapped[str] = mapped_column(String(16))
    comment: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class DeploymentAuditRecord(Base):
    """Append-only deployment audit event. Never stores tokens, secrets, or raw repo content."""

    __tablename__ = "deployment_audit"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    deployment_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    actor_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    request_id: Mapped[str] = mapped_column(String(64))
    safe_metadata: Mapped[str] = mapped_column(String(1024), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class DeploymentTripwireRecord(Base):
    """A persisted tripwire activation, created only after a verified merge. Unique per (deployment,
    trace) so activation is idempotent; status flips to disabled/retired on rollback/retirement."""

    __tablename__ = "deployment_tripwires"
    __table_args__ = (
        UniqueConstraint("deployment_id", "trace_identifier", name="uq_deployment_tripwire"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    deployment_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    decoy_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    trace_identifier: Mapped[str] = mapped_column(String(128), index=True)
    target_path: Mapped[str] = mapped_column(String(2048))
    commit_sha: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="active")
    activated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class DeploymentJobRecord(Base):
    """Async deployment work (execute/verify/retire/rollback). One open job per type per deployment
    (unique) prevents duplicate PR creation under retries or concurrent workers."""

    __tablename__ = "deployment_jobs"
    __table_args__ = (
        UniqueConstraint("deployment_id", "job_type", name="uq_deployment_job"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    deployment_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    job_type: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16), index=True, default="pending")
    correlation_id: Mapped[str] = mapped_column(String(64))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    leased_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, default=_now)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DatabaseConnectorRecord(Base):
    """A PostgreSQL connector. The credential is stored encrypted, never in plaintext."""

    __tablename__ = "database_connectors"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    name: Mapped[str] = mapped_column(String(128))
    engine: Mapped[str] = mapped_column(String(16), default="postgresql")
    host_reference: Mapped[str] = mapped_column(String(512))
    database_name: Mapped[str] = mapped_column(String(255))
    # Encrypted credential (or secret-manager reference) + the key version used. Never plaintext.
    secret_ciphertext: Mapped[str] = mapped_column(Text)
    secret_key_version: Mapped[str] = mapped_column(String(32))
    ssl_mode: Mapped[str] = mapped_column(String(16), default="require")
    status: Mapped[str] = mapped_column(String(16), index=True, default="pending")
    read_only_mode: Mapped[bool] = mapped_column(default=True)
    created_by_actor_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_schema_sync_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    safe_error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class DatabaseSchemaSnapshotRecord(Base):
    """A captured schema snapshot (metadata only — never full table contents)."""

    __tablename__ = "database_schema_snapshots"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    connector_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    database_version: Mapped[str] = mapped_column(String(128))
    snapshot_hash: Mapped[str] = mapped_column(String(64), index=True)
    data: Mapped[str] = mapped_column(Text)  # serialized SchemaSnapshot (metadata only)


class DatabaseHoneyDeploymentRecord(Base):
    """A reviewable, reversible synthetic-row deployment into one approved table."""

    __tablename__ = "database_honey_deployments"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    connector_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    schema_snapshot_id: Mapped[UUID] = mapped_column(Uuid)
    target_schema: Mapped[str] = mapped_column(String(255))
    target_table: Mapped[str] = mapped_column(String(255))
    decoy_type: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), index=True)
    requested_by_actor_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    approved_by_actor_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    preview_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    preview_data: Mapped[str | None] = mapped_column(Text, nullable=True)
    replaced_by_deployment_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    monitoring_activated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deployed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    safe_failure_message: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class DatabaseHoneyRecordRecord(Base):
    """One inserted synthetic row, owned by a deployment. Unique per (deployment, fingerprint) so a
    retried insert never duplicates. Serves as the tripwire registry (status active/retired)."""

    __tablename__ = "database_honey_records"
    __table_args__ = (
        UniqueConstraint("deployment_id", "row_fingerprint", name="uq_honey_record_fingerprint"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    deployment_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    decoy_id: Mapped[UUID] = mapped_column(Uuid, index=True, default=uuid4)
    trace_id: Mapped[str] = mapped_column(String(128), index=True)
    target_primary_key: Mapped[str] = mapped_column(Text)  # JSON {col: value}
    row_fingerprint: Mapped[str] = mapped_column(String(64))
    inserted_values_encrypted: Mapped[str] = mapped_column(Text)
    verification_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="planned")
    inserted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class DatabaseHoneyJobRecord(Base):
    """Async database-honey work (deploy/verify/retire/rollback/rotate). One open job per type per
    deployment (unique) prevents duplicate insertion under retries or concurrent workers."""

    __tablename__ = "database_honey_jobs"
    __table_args__ = (
        UniqueConstraint("deployment_id", "job_type", name="uq_honey_job"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    deployment_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    job_type: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16), index=True, default="pending")
    correlation_id: Mapped[str] = mapped_column(String(64))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, default=_now)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DatabaseHoneyAuditRecord(Base):
    """Append-only audit for database-honey operations. Never stores credentials or full rows."""

    __tablename__ = "database_honey_audit"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    deployment_id: Mapped[UUID | None] = mapped_column(Uuid, index=True, nullable=True)
    connector_id: Mapped[UUID | None] = mapped_column(Uuid, index=True, nullable=True)
    actor_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    request_id: Mapped[str] = mapped_column(String(64))
    safe_metadata: Mapped[str] = mapped_column(String(1024), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class RagConnectorRecord(Base):
    """A vector-store connector. Credentials are stored encrypted, never in plaintext."""

    __tablename__ = "rag_connectors"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    connector_type: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(128))
    secret_ciphertext: Mapped[str] = mapped_column(Text)
    secret_key_version: Mapped[str] = mapped_column(String(32))
    index_or_collection: Mapped[str] = mapped_column(String(255))
    namespace: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(16), index=True, default="pending")
    created_by_actor_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    safe_error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class McpConnectorRecord(Base):
    """An MCP server connector. Any secret is stored encrypted, never in plaintext."""

    __tablename__ = "mcp_connectors"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    name: Mapped[str] = mapped_column(String(128))
    server_reference: Mapped[str] = mapped_column(String(512))
    transport_type: Mapped[str] = mapped_column(String(32))
    secret_ciphertext: Mapped[str | None] = mapped_column(Text, nullable=True)
    secret_key_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(16), index=True, default="pending")
    created_by_actor_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    last_tested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    safe_error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class AiTripwireDeploymentRecord(Base):
    """A reviewable, reversible RAG/MCP tripwire deployment. The deployed content is inert."""

    __tablename__ = "ai_tripwire_deployments"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    surface_type: Mapped[str] = mapped_column(String(16), index=True)
    connector_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    target_collection: Mapped[str] = mapped_column(String(255))
    decoy_kind: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), index=True)
    trace_id: Mapped[str] = mapped_column(String(128), index=True)
    external_asset_id: Mapped[str | None] = mapped_column(String(512), nullable=True)
    requested_by_actor_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    approved_by_actor_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    preview_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    preview_data: Mapped[str | None] = mapped_column(Text, nullable=True)
    verification_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    monitoring_activated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deployed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    safe_failure_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    safe_failure_message: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class AiTripwireEventRecord(Base):
    """A trusted, minimized AI tripwire event. Never stores prompts, chunks, outputs, embeddings."""

    __tablename__ = "ai_tripwire_events"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    deployment_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    trace_id: Mapped[str] = mapped_column(String(128), index=True)
    surface_type: Mapped[str] = mapped_column(String(16))
    event_type: Mapped[str] = mapped_column(String(48), index=True)
    source_id: Mapped[str] = mapped_column(String(256))
    monitor_identity: Mapped[str] = mapped_column(String(128))
    confidence: Mapped[float] = mapped_column()
    minimized_metadata: Mapped[str] = mapped_column(String(1024), default="")
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class AiTripwireJobRecord(Base):
    """Async AI-tripwire work (deploy/verify/retire). Unique per deployment+type -> no duplicate
    external assets under retries or concurrent workers."""

    __tablename__ = "ai_tripwire_jobs"
    __table_args__ = (
        UniqueConstraint("deployment_id", "job_type", name="uq_ai_tripwire_job"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    deployment_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    job_type: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16), index=True, default="pending")
    correlation_id: Mapped[str] = mapped_column(String(64))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, default=_now)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AiTripwireAuditRecord(Base):
    """Append-only AI-tripwire audit. Never stores secrets, prompts, documents, or model output."""

    __tablename__ = "ai_tripwire_audit"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    deployment_id: Mapped[UUID | None] = mapped_column(Uuid, index=True, nullable=True)
    connector_id: Mapped[UUID | None] = mapped_column(Uuid, index=True, nullable=True)
    actor_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    request_id: Mapped[str] = mapped_column(String(64))
    safe_metadata: Mapped[str] = mapped_column(String(1024), default="")
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


class BrowserSensorRecord(Base):
    """A managed browser extension/device identity. The signing secret is stored encrypted; the
    scoped ingest API key is a separate credential and is never reused from the dashboard."""

    __tablename__ = "browser_sensors"
    __table_args__ = (
        UniqueConstraint("sensor_public_id", name="uq_browser_sensor_public_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    sensor_public_id: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(128))
    installation_id: Mapped[str] = mapped_column(String(128), index=True)
    device_label: Mapped[str | None] = mapped_column(String(128), nullable=True)
    browser_family: Mapped[str] = mapped_column(String(32))
    extension_version: Mapped[str] = mapped_column(String(32))
    secret_ciphertext: Mapped[str] = mapped_column(Text)
    secret_key_version: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16), index=True, default="pending")
    api_key_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class BrowserEnrollmentTokenRecord(Base):
    """A one-time, short-lived enrollment token. Only its hash is stored; the plaintext is shown
    once. Consumed atomically at enrollment so it can never be replayed."""

    __tablename__ = "browser_enrollment_tokens"
    __table_args__ = (
        UniqueConstraint("token_hash", name="uq_browser_enrollment_token_hash"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), index=True)
    created_by_actor_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    consumed_by_sensor_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class BrowserAiPolicyRecord(Base):
    """The organization's browser AI policy. One current row per organization; policy_version is
    monotonic so a downgrade can be detected and rejected."""

    __tablename__ = "browser_ai_policies"
    __table_args__ = (
        UniqueConstraint("organization_id", name="uq_browser_ai_policy_org"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    enabled: Mapped[bool] = mapped_column(default=False)
    trace_match_mode: Mapped[str] = mapped_column(String(16), default="exact")
    local_only_mode: Mapped[bool] = mapped_column(default=False)
    event_reporting_enabled: Mapped[bool] = mapped_column(default=True)
    show_user_notification: Mapped[bool] = mapped_column(default=True)
    allow_pause: Mapped[bool] = mapped_column(default=True)
    min_extension_version: Mapped[str] = mapped_column(String(32), default="0.1.0")
    policy_version: Mapped[int] = mapped_column(Integer, default=1)
    # JSON blob of the domain rules (domain + classification). Bounded; contains no secrets.
    rules_data: Mapped[str] = mapped_column(Text, default="[]")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class BrowserEventRecord(Base):
    """A trusted, minimized browser paste event. Never stores pasted text, conversation, or
    model output — only trace id, destination classification, and bounded safe metadata."""

    __tablename__ = "browser_events"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    browser_sensor_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    trace_id: Mapped[str] = mapped_column(String(128), index=True)
    destination_domain: Mapped[str] = mapped_column(String(253))
    destination_classification: Mapped[str] = mapped_column(String(16), index=True)
    event_type: Mapped[str] = mapped_column(String(48), index=True)
    match_method: Mapped[str] = mapped_column(String(16))
    confidence: Mapped[float] = mapped_column()
    extension_version: Mapped[str] = mapped_column(String(32))
    policy_version: Mapped[int] = mapped_column(Integer)
    excerpt_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    minimized_metadata: Mapped[str] = mapped_column(String(1024), default="")
    correlation_id: Mapped[str] = mapped_column(String(64), index=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class BrowserSensorAuditRecord(Base):
    """Append-only browser-sensor audit. Never stores secrets, signatures, pasted text, or
    conversation content."""

    __tablename__ = "browser_sensor_audit"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    organization_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    browser_sensor_id: Mapped[UUID | None] = mapped_column(Uuid, index=True, nullable=True)
    actor_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    request_id: Mapped[str] = mapped_column(String(64))
    safe_metadata: Mapped[str] = mapped_column(String(1024), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
