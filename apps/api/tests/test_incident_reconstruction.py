from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.models.domain.operations import AlertEvidence, MonitorType, NormalizedAlert, Severity
from app.services.incident_reconstruction import IncidentConfig, IncidentReconstructionEngine


def alert(
    monitor: MonitorType = MonitorType.REPOSITORY, trace: str = "DFG-A", at: datetime | None = None
) -> NormalizedAlert:
    return NormalizedAlert(
        alert_id=uuid4(),
        trace_identifier=trace,
        decoy_id=uuid4(),
        severity=Severity.HIGH,
        title="trace",
        summary="observed",
        source_monitor=monitor,
        confidence=0.9,
        first_seen=at or datetime.now(UTC),
        last_seen=at or datetime.now(UTC),
        event_count=1,
        deduplication_key=f"{trace}:id:{monitor.value}:path:repository:content_access",
        affected_placement_id=uuid4(),
        affected_decoy_type="secret",
        evidence=(AlertEvidence(excerpt="DFG-A", digest="a" * 64, location="path"),),
        raw_event_ids=(uuid4(),),
        recommended_actions=("review",),
        correlation_id=uuid4(),
    )


def test_single_alert_creates_stable_repository_incident() -> None:
    item = alert()
    incident = IncidentReconstructionEngine().reconstruct((item,))[0]
    assert incident.incident_type.value == "repository_exposure"
    assert incident.timeline[0].sequence == 1
    assert incident.evidence_summary[0].excerpt == "DFG-A"
    assert incident.gpt_context_bundle.timeline == incident.timeline


def test_related_alerts_group_and_cross_surface_escalates() -> None:
    first = alert(trace="DFG-X")
    second = alert(
        MonitorType.TEXT_PAYLOAD, trace="DFG-X", at=first.first_seen + timedelta(seconds=10)
    )
    second = second.model_copy(
        update={
            "decoy_id": first.decoy_id,
            "affected_placement_id": first.affected_placement_id,
            "correlation_id": first.correlation_id,
        }
    )
    incident = IncidentReconstructionEngine().reconstruct((first, second))[0]
    assert incident.incident_type.value == "multi_surface_exposure"
    assert incident.severity.value == "critical"
    assert len(incident.timeline) == 2


def test_unrelated_or_out_of_window_alerts_do_not_group_and_empty_is_safe() -> None:
    first = alert(trace="DFG-1")
    second = alert(trace="DFG-2", at=first.first_seen + timedelta(hours=2))
    incidents = IncidentReconstructionEngine().reconstruct(
        (first, second), IncidentConfig(correlation_window_seconds=60)
    )
    assert len(incidents) == 2
    assert IncidentReconstructionEngine().reconstruct(()) == ()
