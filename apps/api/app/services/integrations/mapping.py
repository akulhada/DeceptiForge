# Purpose: map DeceptiForge source objects into minimized canonical security events.
# Responsibilities: build a SecurityEventEnvelope from an alert / incident / coverage gap /
#   operational signal using only deterministic, non-sensitive identifiers and summaries — never raw
#   evidence, prompts, rows, or secrets. The GPT narrative is attached only when explicitly allowed
#   and is labeled non-authoritative. Deterministic. Dependencies: integrations domain, Severity.
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.models.domain.integrations import (
    EventType,
    SecurityEventEnvelope,
    SourceType,
    source_for_event,
)
from app.models.domain.operations import Severity


def _base(
    *, event_type: EventType, org: str, occurred_at: datetime, severity: Severity,
    source_id: str, title: str, summary: str, confidence: float,
) -> dict[str, Any]:
    return {
        "event_type": event_type,
        "event_id": f"{event_type.value}:{source_id}",
        "organization_id": org[:64],
        "occurred_at": occurred_at,
        "severity": severity,
        "confidence": confidence,
        "title": title[:256],
        "summary": summary[:1024],
        "source_object_type": source_for_event(event_type),
        "source_object_id": source_id[:128],
    }


def build_alert_event(
    *, event_type: EventType, org: str, occurred_at: datetime, alert_id: str, severity: Severity,
    title: str, summary: str, confidence: float, trace_ids: tuple[str, ...] = (),
    decoy_types: tuple[str, ...] = (), affected_surfaces: tuple[str, ...] = (),
    recommended_actions: tuple[str, ...] = (), correlation_ids: tuple[str, ...] = (),
    evidence_summary: str = "",
) -> SecurityEventEnvelope:
    data = _base(
        event_type=event_type, org=org, occurred_at=occurred_at, severity=severity,
        source_id=alert_id, title=title, summary=summary, confidence=confidence,
    )
    return SecurityEventEnvelope(
        **data, trace_ids=trace_ids[:20], decoy_types=decoy_types[:20],
        affected_surfaces=affected_surfaces[:20], recommended_actions=recommended_actions[:10],
        request_or_correlation_ids=correlation_ids[:10],
        deterministic_evidence_summary=evidence_summary[:1024],
    )


def build_incident_event(
    *, event_type: EventType, org: str, occurred_at: datetime, incident_id: str, severity: Severity,
    title: str, summary: str, confidence: float, incident_status: str,
    affected_surfaces: tuple[str, ...] = (), trace_ids: tuple[str, ...] = (),
    recommended_actions: tuple[str, ...] = (), evidence_summary: str = "",
    narrative: str | None = None,
) -> SecurityEventEnvelope:
    data = _base(
        event_type=event_type, org=org, occurred_at=occurred_at, severity=severity,
        source_id=incident_id, title=title, summary=summary, confidence=confidence,
    )
    metadata = {"narrative_label": "ai_generated_non_authoritative"} if narrative else {}
    return SecurityEventEnvelope(
        **data, incident_status=incident_status[:32], affected_surfaces=affected_surfaces[:20],
        trace_ids=trace_ids[:20], recommended_actions=recommended_actions[:10],
        deterministic_evidence_summary=evidence_summary[:1024],
        narrative_summary=(narrative[:2048] if narrative else None), metadata=metadata,
    )


def build_coverage_event(
    *, event_type: EventType, org: str, occurred_at: datetime, surface_id: str, severity: Severity,
    title: str, summary: str, affected_surfaces: tuple[str, ...] = (),
    recommended_actions: tuple[str, ...] = (),
) -> SecurityEventEnvelope:
    data = _base(
        event_type=event_type, org=org, occurred_at=occurred_at, severity=severity,
        source_id=surface_id, title=title, summary=summary, confidence=1.0,
    )
    return SecurityEventEnvelope(
        **data, affected_surfaces=affected_surfaces[:20],
        recommended_actions=recommended_actions[:10],
    )


def build_operational_event(
    *, event_type: EventType, org: str, occurred_at: datetime, object_id: str, severity: Severity,
    title: str, summary: str, connector_id: str | None = None, repository_id: str | None = None,
) -> SecurityEventEnvelope:
    data = _base(
        event_type=event_type, org=org, occurred_at=occurred_at, severity=severity,
        source_id=object_id, title=title, summary=summary, confidence=1.0,
    )
    return SecurityEventEnvelope(
        **data, connector_id=(connector_id[:64] if connector_id else None),
        repository_id=(repository_id[:64] if repository_id else None),
    )


def contains_no_raw_evidence(envelope: SecurityEventEnvelope) -> bool:
    """Cheap guard used in tests: the canonical event exposes only bounded summaries + ids, never a
    field that could carry raw evidence/secret content."""
    banned = ("password", "secret", "token", "BEGIN RSA", "-----BEGIN")
    blob = envelope.model_dump_json()
    return not any(b.lower() in blob.lower() for b in banned)


def source_object_type(event_type: EventType) -> SourceType:
    return source_for_event(event_type)
