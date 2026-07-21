# Purpose: verify integration domain enums, event->source mapping, schema version, and envelope
#   bounds.
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.models.domain.integrations import (
    SCHEMA_VERSION,
    EventType,
    SecurityEventEnvelope,
    SourceType,
    source_for_event,
)
from app.models.domain.operations import Severity


def test_schema_version_stable() -> None:
    assert SCHEMA_VERSION == "df-security-event-v1"


def test_event_source_mapping() -> None:
    assert source_for_event(EventType.ALERT_CREATED) == SourceType.ALERT
    assert source_for_event(EventType.INCIDENT_RESOLVED) == SourceType.INCIDENT
    assert source_for_event(EventType.COVERAGE_CRITICAL_GAP) == SourceType.COVERAGE_GAP
    assert source_for_event(EventType.CONNECTOR_UNHEALTHY) == SourceType.OPERATIONAL_EVENT


def test_envelope_bounds_arrays() -> None:
    with pytest.raises(ValidationError):
        SecurityEventEnvelope(
            event_id="e",
            event_type=EventType.ALERT_CREATED,
            organization_id="o",
            occurred_at="2026-07-19T00:00:00Z",
            severity=Severity.HIGH,
            title="t",
            summary="s",
            source_object_type=SourceType.ALERT,
            source_object_id="a",
            trace_ids=tuple(str(i) for i in range(50)),  # exceeds max_length=20
        )
