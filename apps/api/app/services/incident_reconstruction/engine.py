"""Deterministic correlation of normalized alerts into evidence-minimizing incidents."""

from dataclasses import dataclass
from datetime import timedelta
from uuid import NAMESPACE_URL, uuid5

from app.models.domain.operations import (
    DetectionSource,
    GptSummaryContextBundle,
    IncidentType,
    NormalizedAlert,
    ReconstructedIncident,
    ReconstructedTimelineEvent,
    Severity,
)


@dataclass(frozen=True)
class IncidentConfig:
    correlation_window_seconds: int = 3600


class IncidentReconstructionEngine:
    def reconstruct(
        self, alerts: tuple[NormalizedAlert, ...], config: IncidentConfig | None = None
    ) -> tuple[ReconstructedIncident, ...]:
        config = config or IncidentConfig()
        groups: list[list[NormalizedAlert]] = []
        for alert in sorted(alerts, key=lambda item: (item.first_seen, str(item.alert_id))):
            for group in groups:
                if self._related(alert, group, config):
                    group.append(alert)
                    break
            else:
                groups.append([alert])
        return tuple(self._build(group) for group in groups)

    @staticmethod
    def _related(
        alert: NormalizedAlert, group: list[NormalizedAlert], config: IncidentConfig
    ) -> bool:
        latest = max(item.last_seen for item in group)
        if alert.first_seen - latest > timedelta(seconds=config.correlation_window_seconds):
            return False
        return any(
            alert.trace_identifier == item.trace_identifier
            or alert.decoy_id == item.decoy_id
            or alert.affected_placement_id == item.affected_placement_id
            or alert.correlation_id == item.correlation_id
            or (
                alert.source_monitor == item.source_monitor
                and alert.deduplication_key.split(":")[-2] == item.deduplication_key.split(":")[-2]
            )
            for item in group
        )

    def _build(self, alerts: list[NormalizedAlert]) -> ReconstructedIncident:
        alerts = sorted(alerts, key=lambda item: (item.first_seen, str(item.alert_id)))
        kind = self._kind(alerts)
        timeline = tuple(
            ReconstructedTimelineEvent(
                sequence=index,
                timestamp=alert.first_seen,
                source=DetectionSource(alert.deduplication_key.split(":")[-2]),
                monitor_type=alert.source_monitor,
                trace_identifier=alert.trace_identifier,
                decoy_id=alert.decoy_id,
                placement_id=alert.affected_placement_id,
                summary=alert.summary,
                evidence=alert.evidence[0],
                confidence=alert.confidence,
            )
            for index, alert in enumerate(alerts, 1)
        )
        severity = self._severity(alerts, kind)
        hypothesis = self._hypothesis(kind)
        actions = self._actions(kind)
        traces = tuple(sorted({alert.trace_identifier for alert in alerts}))
        key = ":".join(traces)
        return ReconstructedIncident(
            incident_id=uuid5(NAMESPACE_URL, key),
            title=f"{kind.value.replace('_', ' ').title()} detection",
            severity=severity,
            confidence=round(sum(alert.confidence for alert in alerts) / len(alerts), 3),
            incident_type=kind,
            first_seen=alerts[0].first_seen,
            last_seen=max(alert.last_seen for alert in alerts),
            involved_alert_ids=tuple(alert.alert_id for alert in alerts),
            involved_decoy_ids=tuple(sorted({alert.decoy_id for alert in alerts}, key=str)),
            involved_trace_ids=traces,
            involved_placement_ids=tuple(
                sorted({alert.affected_placement_id for alert in alerts}, key=str)
            ),
            affected_surfaces=tuple(sorted({alert.source_monitor.value for alert in alerts})),
            timeline=timeline,
            evidence_summary=tuple(item for alert in alerts for item in alert.evidence)[:10],
            root_cause_hypothesis=hypothesis,
            recommended_actions=actions,
            correlation_keys=tuple(alert.deduplication_key for alert in alerts),
            correlation_reasons=(
                (
                    "Alerts share a trace, decoy, placement, correlation ID, or source/monitor "
                    "within the configured window."
                ),
            ),
            escalation_hints=(
                (
                    "Escalate to security operations."
                    if severity in {Severity.HIGH, Severity.CRITICAL}
                    else "Review during normal triage."
                ),
            ),
            false_positive_notes=tuple(
                note for alert in alerts for note in alert.false_positive_notes
            ),
            gpt_context_bundle=GptSummaryContextBundle(
                incident_type=kind,
                timeline=timeline,
                root_cause_hypothesis=hypothesis,
                recommended_actions=actions,
            ),
        )

    @staticmethod
    def _kind(alerts: list[NormalizedAlert]) -> IncidentType:
        monitors = {alert.source_monitor.value for alert in alerts}
        if len(monitors) > 1:
            return IncidentType.MULTI_SURFACE_EXPOSURE
        monitor = next(iter(monitors))
        if monitor == "text_payload":
            return IncidentType.AI_PASTE_LEAK
        if monitor == "repository":
            return IncidentType.REPOSITORY_EXPOSURE
        if monitor == "database_payload":
            return IncidentType.DATABASE_EXPORT
        if monitor == "file_content":
            return IncidentType.FILE_COPY_OR_SYNC
        return (
            IncidentType.REPEATED_PROBE if len(alerts) > 1 else IncidentType.UNKNOWN_TRIPWIRE_TOUCH
        )

    @staticmethod
    def _severity(alerts: list[NormalizedAlert], kind: IncidentType) -> Severity:
        levels = {
            Severity.INFO: 0,
            Severity.LOW: 1,
            Severity.MEDIUM: 2,
            Severity.HIGH: 3,
            Severity.CRITICAL: 4,
        }
        level = (
            max(levels[alert.severity] for alert in alerts)
            + int(len(alerts) >= 3)
            + int(kind is IncidentType.MULTI_SURFACE_EXPOSURE)
        )
        return tuple(levels)[min(level, 4)]

    @staticmethod
    def _hypothesis(kind: IncidentType) -> str:
        return {
            IncidentType.AI_PASTE_LEAK: (
                "Possible sensitive data paste into an AI or external text workflow."
            ),
            IncidentType.REPOSITORY_EXPOSURE: (
                "Possible repository exposure, accidental commit, or copied source content."
            ),
            IncidentType.DATABASE_EXPORT: (
                "Possible database export, BI workflow, or application-layer data access."
            ),
            IncidentType.FILE_COPY_OR_SYNC: (
                "Possible file copy or synchronization to another surface."
            ),
            IncidentType.MULTI_SURFACE_EXPOSURE: (
                "Possible propagation of sensitive-looking data across systems."
            ),
        }.get(kind, "Tripwire activity requires validation against surrounding access evidence.")

    @staticmethod
    def _actions(kind: IncidentType) -> tuple[str, ...]:
        return {
            IncidentType.AI_PASTE_LEAK: (
                "Review browser or session activity.",
                "Inspect the source document or export.",
            ),
            IncidentType.REPOSITORY_EXPOSURE: (
                "Inspect commit history.",
                "Review repository visibility and developer access.",
            ),
            IncidentType.DATABASE_EXPORT: (
                "Inspect query and export logs.",
                "Review service-account activity.",
            ),
            IncidentType.MULTI_SURFACE_EXPOSURE: (
                "Prioritize containment.",
                "Search all systems for involved trace identifiers.",
            ),
        }.get(kind, ("Review related monitor activity.", "Validate the affected placement."))
