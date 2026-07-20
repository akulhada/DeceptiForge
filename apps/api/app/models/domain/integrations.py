# Purpose: domain contract for SIEM/SOAR security integrations and the canonical export event.
# Responsibilities: define integration types/status, delivery status, source/event types, payload
#   profiles, retry classification, and the versioned SecurityEventEnvelope (deterministic fields
#   authoritative; GPT narrative optional + labeled; no raw secrets/evidence; bounded). No
#   transport, persistence, or scoring here. Dependencies: DomainModel base, Severity.
from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field

from app.models.domain.base import DomainModel
from app.models.domain.operations import Severity

# Bump when the canonical envelope shape changes. Receivers key on this.
SCHEMA_VERSION = "df-security-event-v1"


class IntegrationType(StrEnum):
    GENERIC_WEBHOOK = "generic_webhook"
    SPLUNK_HEC = "splunk_hec"
    MICROSOFT_SENTINEL = "microsoft_sentinel"
    ELASTIC = "elastic"
    DATADOG = "datadog"


class IntegrationStatus(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    DEGRADED = "degraded"
    DISABLED = "disabled"
    REVOKED = "revoked"


class SourceType(StrEnum):
    ALERT = "alert"
    INCIDENT = "incident"
    COVERAGE_GAP = "coverage_gap"
    OPERATIONAL_EVENT = "operational_event"


class DeliveryStatus(StrEnum):
    QUEUED = "queued"
    DELIVERING = "delivering"
    DELIVERED = "delivered"
    RETRYING = "retrying"
    FAILED = "failed"
    DEAD_LETTERED = "dead_lettered"


class PayloadProfile(StrEnum):
    MINIMAL = "minimal"
    STANDARD = "standard"
    ANALYST = "analyst"
    COMPLIANCE_SUMMARY = "compliance_summary"


class EventType(StrEnum):
    ALERT_CREATED = "deceptiforge.alert.created"
    ALERT_UPDATED = "deceptiforge.alert.updated"
    ALERT_ESCALATED = "deceptiforge.alert.escalated"
    INCIDENT_CREATED = "deceptiforge.incident.created"
    INCIDENT_UPDATED = "deceptiforge.incident.updated"
    INCIDENT_RESOLVED = "deceptiforge.incident.resolved"
    INCIDENT_STALE = "deceptiforge.incident.stale"
    INCIDENT_SUPERSEDED = "deceptiforge.incident.superseded"
    COVERAGE_CRITICAL_GAP = "deceptiforge.coverage.critical_gap"
    COVERAGE_SCORE_DROP = "deceptiforge.coverage.score_drop"
    COVERAGE_SENSOR_DEGRADED = "deceptiforge.coverage.sensor_degraded"
    COVERAGE_DECOY_EXPIRED = "deceptiforge.coverage.decoy_expired"
    MONITOR_ACTIVATION_FAILED = "deceptiforge.monitor.activation_failed"
    CONNECTOR_UNHEALTHY = "deceptiforge.connector.unhealthy"
    RETENTION_FAILED = "deceptiforge.retention.failed"
    RECONSTRUCTION_FAILED = "deceptiforge.reconstruction.failed"
    DELIVERY_FAILED = "deceptiforge.integration.delivery_failed"


_SOURCE_FOR_EVENT: dict[str, SourceType] = {}
for _e in EventType:
    if _e.value.startswith("deceptiforge.alert"):
        _SOURCE_FOR_EVENT[_e.value] = SourceType.ALERT
    elif _e.value.startswith("deceptiforge.incident"):
        _SOURCE_FOR_EVENT[_e.value] = SourceType.INCIDENT
    elif _e.value.startswith("deceptiforge.coverage"):
        _SOURCE_FOR_EVENT[_e.value] = SourceType.COVERAGE_GAP
    else:
        _SOURCE_FOR_EVENT[_e.value] = SourceType.OPERATIONAL_EVENT


def source_for_event(event_type: EventType) -> SourceType:
    return _SOURCE_FOR_EVENT[event_type.value]


class RetryDecision(StrEnum):
    RETRY = "retry"
    PERMANENT = "permanent"
    SUCCESS = "success"


class SecurityEventEnvelope(DomainModel):
    """The versioned canonical event delivered to every destination. Deterministic fields are
    authoritative; narrative_summary is optional and separately labeled. No raw secrets/evidence;
    bounded strings + arrays."""

    schema_version: str = SCHEMA_VERSION
    event_id: str = Field(max_length=128)
    event_type: EventType
    organization_id: str = Field(max_length=64)
    occurred_at: datetime
    severity: Severity
    confidence: float = Field(ge=0, le=1, default=1.0)
    title: str = Field(max_length=256)
    summary: str = Field(max_length=1024)
    source_system: str = Field(default="deceptiforge", max_length=32)
    source_object_type: SourceType
    source_object_id: str = Field(max_length=128)
    trace_ids: tuple[str, ...] = Field(default=(), max_length=20)
    decoy_types: tuple[str, ...] = Field(default=(), max_length=20)
    affected_surfaces: tuple[str, ...] = Field(default=(), max_length=20)
    repository_id: str | None = Field(default=None, max_length=64)
    connector_id: str | None = Field(default=None, max_length=64)
    incident_status: str | None = Field(default=None, max_length=32)
    recommended_actions: tuple[str, ...] = Field(default=(), max_length=10)
    deterministic_evidence_summary: str = Field(default="", max_length=1024)
    # Optional GPT narrative — clearly labeled, never authoritative, only when policy allows.
    narrative_summary: str | None = Field(default=None, max_length=2048)
    request_or_correlation_ids: tuple[str, ...] = Field(default=(), max_length=10)
    links: dict[str, str] = Field(default_factory=dict)
    metadata: dict[str, str] = Field(default_factory=dict)


class RoutingFilter(DomainModel):
    """Validated declarative routing rules. No executable expressions."""

    event_types: tuple[str, ...] = ()
    minimum_severity: Severity = Severity.INFO
    surface_types: tuple[str, ...] = ()
    include_narrative: bool = False
    include_coverage_events: bool = True
    include_operational_events: bool = True
    payload_profile: PayloadProfile = PayloadProfile.MINIMAL


class DeliveryResult(DomainModel):
    """Normalized adapter result. Never carries the credential or the full response body."""

    decision: RetryDecision
    response_status: int | None = None
    safe_error_code: str | None = Field(default=None, max_length=64)
    retry_after_seconds: int | None = None
