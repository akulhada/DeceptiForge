# Purpose: model security observations, incidents, timelines, and coverage. Responsibilities: define immutable operational facts and assessments without collection, correlation, or remediation behavior. Future modules: add evidence providers and workflow state in separate aggregates.
from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import Field

from app.models.domain.base import (
    AlertId,
    CoverageId,
    DecoyId,
    DomainModel,
    IncidentId,
    OrganizationId,
    RepositoryId,
    TimelineEventId,
)
from app.models.domain.organization import RiskLevel


class Severity(StrEnum):
    """Alert urgency vocabulary independent of incident risk."""

    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class DetectionSource(StrEnum):
    """System boundary that emitted an observation."""

    REPOSITORY = "repository"
    DATABASE = "database"
    DOCUMENT = "document"
    BROWSER = "browser"
    AGENT = "agent"
    MCP = "mcp"
    SYSTEM = "system"


class TriggerType(StrEnum):
    """Condition that promoted an observation into an alert."""

    DECOY_ACCESSED = "decoy_accessed"
    UNEXPECTED_ACCESS = "unexpected_access"
    POLICY_VIOLATION = "policy_violation"
    ANOMALOUS_BEHAVIOR = "anomalous_behavior"
    INTEGRITY_CHANGE = "integrity_change"


class DetectionMethod(StrEnum):
    """Evidence mechanism used to detect the triggering activity."""

    CANARY_TOKEN = "canary_token"
    CONTENT_ACCESS = "content_access"
    AUDIT_LOG = "audit_log"
    BROWSER_TELEMETRY = "browser_telemetry"
    TOOL_TELEMETRY = "tool_telemetry"
    DATABASE_AUDIT = "database_audit"


class MonitorType(StrEnum):
    FILE_CONTENT = "file_content"
    REPOSITORY = "repository"
    DATABASE_PAYLOAD = "database_payload"
    TEXT_PAYLOAD = "text_payload"


class MonitorHealthStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    DEGRADED = "degraded"
    FAILED = "failed"


class TimelineAction(StrEnum):
    """Actions that can be represented as a timeline fact."""

    READ = "read"
    COPY = "copy"
    EXPORT = "export"
    PASTE = "paste"
    INDEX = "index"
    EMBED = "embed"
    AUTHENTICATION = "authentication"
    TOOL_CALL = "tool_call"
    DATABASE_QUERY = "database_query"
    PACKAGE_INSTALL = "package_install"
    DOCUMENT_ACCESS = "document_access"


class EventAttribute(DomainModel):
    """A safe, typed context attribute for a timeline event.

    Purpose: retain structured event context without unbounded arbitrary payloads.
    Fields: key and redacted string value.
    Relationships: embedded by TimelineEvent only.
    Future extensibility: add classified value references for larger or sensitive evidence.
    """

    key: str = Field(min_length=1, max_length=128)
    value: str = Field(min_length=1, max_length=2048)


class AssetReference(DomainModel):
    """A stable reference to an affected security asset.

    Purpose: identify assets without coupling incidents to a storage implementation.
    Fields: asset kind, opaque ID, and display label.
    Relationships: embedded by Incident and may refer to a decoy or external asset.
    Future extensibility: add provider and ownership metadata as explicit fields.
    """

    kind: str = Field(min_length=1, max_length=128)
    asset_id: str = Field(min_length=1, max_length=512)
    label: str = Field(min_length=1, max_length=512)


class EvidenceReference(DomainModel):
    """A durable, non-secret pointer to supporting evidence.

    Purpose: preserve forensic links without copying potentially sensitive material.
    Fields: evidence kind, locator, digest, and summary.
    Relationships: embedded by Incident; may support many alerts and timeline events externally.
    Future extensibility: add retention and access-policy references.
    """

    kind: str = Field(min_length=1, max_length=128)
    locator: str = Field(min_length=1, max_length=2048)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    summary: str = Field(min_length=1, max_length=2000)


class TimelineEvent(DomainModel):
    """An immutable observed action in security chronology.

    Purpose: provide the canonical fact record for detection and investigation.
    Fields: action, source, timestamp, target, optional actor/decoy references, confidence, and safe attributes.
    Relationships: may be referenced by Alert and embedded in an Incident timeline snapshot.
    Future extensibility: add correlation IDs and external event IDs without altering action semantics.
    """

    id: TimelineEventId
    organization_id: OrganizationId
    action: TimelineAction
    source: DetectionSource
    timestamp: datetime
    target: AssetReference
    decoy_id: DecoyId | None = None
    actor_reference: str | None = Field(default=None, max_length=512)
    confidence: float = Field(ge=0, le=1)
    attributes: tuple[EventAttribute, ...] = Field(default=(), max_length=30)
    schema_version: int = Field(default=1, ge=1)


class Alert(DomainModel):
    """A normalized detection requiring review or correlation.

    Purpose: preserve one actionable detection independent of incident workflow.
    Fields: severity, source, timestamp, confidence, trigger type, detection method, and event relation.
    Relationships: belongs to Organization; may reference a Decoy, TimelineEvent, and Incident.
    Future extensibility: add acknowledgement workflow in a separate operational aggregate.
    """

    id: AlertId
    organization_id: OrganizationId
    severity: Severity
    source: DetectionSource
    timestamp: datetime
    confidence: float = Field(ge=0, le=1)
    trigger_type: TriggerType
    detection_method: DetectionMethod
    timeline_event_id: TimelineEventId
    decoy_id: DecoyId | None = None
    incident_id: IncidentId | None = None
    schema_version: int = Field(default=1, ge=1)


class Incident(DomainModel):
    """An immutable investigation summary with portable forensic context.

    Purpose: capture the assessed security event without implementing response workflow.
    Fields: timeline, root cause, affected assets, risk, summary, evidence, and recommendations.
    Relationships: belongs to Organization; may include Alerts and Decoys through referenced timeline data.
    Future extensibility: add status, ownership, and remediation tasks as separate workflow aggregates.
    """

    id: IncidentId
    organization_id: OrganizationId
    timeline: tuple[TimelineEvent, ...] = Field(min_length=1)
    root_cause: str = Field(min_length=1, max_length=4000)
    affected_assets: tuple[AssetReference, ...] = Field(min_length=1)
    risk: RiskLevel
    summary: str = Field(min_length=1, max_length=8000)
    evidence: tuple[EvidenceReference, ...] = ()
    recommendations: tuple[str, ...] = Field(default=(), max_length=30)
    schema_version: int = Field(default=1, ge=1)


class Coverage(DomainModel):
    """Measured protection coverage for one organization or repository scope.

    Purpose: report assessment dimensions without defining how they are improved.
    Fields: repository, database, document, AI, and overall normalized coverage scores.
    Relationships: belongs to Organization and may be scoped to Repository.
    Future extensibility: add evaluator version and dimension evidence references.
    """

    id: CoverageId
    organization_id: OrganizationId
    repository_id: RepositoryId | None = None
    repository_coverage: float = Field(ge=0, le=1)
    database_coverage: float = Field(ge=0, le=1)
    document_coverage: float = Field(ge=0, le=1)
    ai_coverage: float = Field(ge=0, le=1)
    overall_coverage: float = Field(ge=0, le=1)
    measured_at: datetime
    schema_version: int = Field(default=1, ge=1)


class TripwireRegistryEntry(DomainModel):
    trace_identifier: str = Field(min_length=1, max_length=128)
    decoy_id: UUID
    placement_id: UUID
    target_location: str = Field(min_length=1, max_length=2048)
    template_id: str = Field(min_length=1, max_length=128)
    decoy_type: str = Field(min_length=1, max_length=128)
    enabled: bool = True


class MonitorRegistration(DomainModel):
    monitor_type: MonitorType
    trace_identifier: str = Field(min_length=1, max_length=128)
    target_location: str = Field(min_length=1, max_length=2048)
    status: MonitorHealthStatus


class MonitorRegistrationPlan(DomainModel):
    registrations: tuple[MonitorRegistration, ...] = ()
    rejected_decoy_ids: tuple[UUID, ...] = ()


class MonitorHealthMetadata(DomainModel):
    monitor_type: MonitorType
    status: MonitorHealthStatus
    detail: str = Field(min_length=1, max_length=1000)


class RawDetectionEvent(DomainModel):
    event_id: UUID
    trace_identifier: str = Field(min_length=1, max_length=128)
    decoy_id: UUID
    monitor_type: MonitorType
    observed_location: str = Field(min_length=1, max_length=2048)
    observed_value_excerpt: str = Field(min_length=1, max_length=256)
    timestamp: datetime
    source: DetectionSource
    confidence: float = Field(ge=0, le=1)
    severity_suggestion: Severity
    evidence_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    detection_method: DetectionMethod
    raw_metadata: tuple[EventAttribute, ...] = ()
    correlation_id: UUID
