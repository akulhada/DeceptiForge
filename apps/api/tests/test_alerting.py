from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.models.domain.operations import (
    DetectionMethod,
    DetectionSource,
    MonitorType,
    RawDetectionEvent,
    Severity,
    TripwireRegistryEntry,
)
from app.services.alerting import AlertingConfig, AlertingPipeline


def event(
    *, location: str = "docs/runbook.md", confidence: float = 1, at: datetime | None = None
) -> RawDetectionEvent:
    return RawDetectionEvent(
        event_id=uuid4(),
        trace_identifier="DFG-ABC123",
        decoy_id=uuid4(),
        monitor_type=MonitorType.REPOSITORY,
        observed_location=location,
        observed_value_excerpt="prefix DFG-ABC123 suffix",
        timestamp=at or datetime.now(UTC),
        source=DetectionSource.REPOSITORY,
        confidence=confidence,
        severity_suggestion=Severity.HIGH,
        evidence_digest="a" * 64,
        detection_method=DetectionMethod.CONTENT_ACCESS,
        correlation_id=uuid4(),
    )


def test_valid_event_creates_enriched_alert_with_minimal_evidence() -> None:
    raw = event()
    tripwire = TripwireRegistryEntry(
        trace_identifier=raw.trace_identifier,
        decoy_id=raw.decoy_id,
        placement_id=uuid4(),
        target_location=".env.example",
        template_id="secret_v1",
        decoy_type="secret",
    )
    alert = AlertingPipeline().ingest(raw, tripwire)

    assert alert is not None and alert.event_count == 1
    assert alert.evidence[0].digest == raw.evidence_digest
    assert alert.recommended_actions and alert.correlation_id == raw.correlation_id


def test_deduplication_window_and_new_location_behavior() -> None:
    first = event()
    pipeline = AlertingPipeline()
    alert = pipeline.ingest(first, None)
    assert alert is not None
    duplicate = event(at=first.timestamp + timedelta(seconds=30))
    duplicate = duplicate.model_copy(
        update={"decoy_id": first.decoy_id, "correlation_id": first.correlation_id}
    )
    updated = pipeline.ingest(duplicate, None, AlertingConfig(deduplication_window_seconds=60))
    separate = pipeline.ingest(event(location="other.md"), None)

    assert updated is not None and updated.event_count == 2
    assert separate is not None and len(pipeline.alerts()) == 2


def test_later_episode_gets_a_new_alert_identity() -> None:
    start = datetime.now(UTC)
    pipeline = AlertingPipeline()
    first = event(at=start)
    first_alert = pipeline.ingest(first, None, AlertingConfig(deduplication_window_seconds=60))
    later = first.model_copy(
        update={"event_id": uuid4(), "timestamp": start + timedelta(minutes=2)}
    )
    later_alert = pipeline.ingest(later, None, AlertingConfig(deduplication_window_seconds=60))

    assert first_alert is not None and later_alert is not None
    assert first_alert.alert_id != later_alert.alert_id
    assert len(pipeline.alerts()) == 2


def test_invalid_event_is_rejected_and_confidence_affects_severity() -> None:
    pipeline = AlertingPipeline()
    assert pipeline.ingest(event(confidence=0.4), None) is None
    high = pipeline.ingest(event(confidence=1), None)
    low = AlertingPipeline().ingest(event(confidence=0.5), None)

    assert high is not None and low is not None
    assert high.severity.value in {"high", "critical"}
    assert low.severity.value in {"medium", "low"}
