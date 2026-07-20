# Purpose: deterministic, declarative routing — decide whether an integration should receive an
#   event, and build the stable idempotency key.
# Responsibilities: validated filtering by event type, minimum severity, surface type, and the
#   coverage/operational/narrative toggles. No executable expressions. Pure. Dependencies:
#   integrations domain, Severity ordering.
from __future__ import annotations

import json

from app.models.domain.integrations import SecurityEventEnvelope, SourceType, source_for_event
from app.models.domain.operations import Severity

_ORDER = {
    Severity.INFO: 0, Severity.LOW: 1, Severity.MEDIUM: 2, Severity.HIGH: 3, Severity.CRITICAL: 4,
}


def severity_at_least(value: Severity, minimum: Severity) -> bool:
    return _ORDER[value] >= _ORDER[minimum]


def matches(
    *,
    routing_json: str,
    minimum_severity: str,
    include_coverage: bool,
    include_operational: bool,
    envelope: SecurityEventEnvelope,
) -> bool:
    if not severity_at_least(envelope.severity, Severity(minimum_severity)):
        return False
    source = source_for_event(envelope.event_type)
    if source == SourceType.COVERAGE_GAP and not include_coverage:
        return False
    if source == SourceType.OPERATIONAL_EVENT and not include_operational:
        return False
    rules = json.loads(routing_json or "{}")
    event_types = rules.get("event_types") or []
    if event_types and envelope.event_type.value not in event_types:
        return False
    surface_types = rules.get("surface_types") or []
    if surface_types and not any(s in surface_types for s in envelope.affected_surfaces):
        return False
    return True


def idempotency_key(
    *, organization_id: str, integration_id: str, source_id: str, event_version: int,
    event_type: str,
) -> str:
    """Stable per (org, integration, source object, version, event type). Event updates bump the
    version and therefore produce a new delivery rather than a silent overwrite."""
    return f"{organization_id}:{integration_id}:{event_type}:{source_id}:v{event_version}"[:200]
