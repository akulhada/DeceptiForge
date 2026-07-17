"""Configurable, deterministic severity scoring."""

from dataclasses import dataclass

from app.models.domain.operations import MonitorType, RawDetectionEvent, Severity


@dataclass(frozen=True)
class AlertingConfig:
    deduplication_window_seconds: int = 900
    high_threshold: float = 70
    critical_threshold: float = 90


class AlertSeverityScorer:
    def severity(
        self, event: RawDetectionEvent, decoy_type: str, placement_priority: float, count: int
    ) -> Severity:
        monitor = {
            MonitorType.DATABASE_PAYLOAD: 25,
            MonitorType.REPOSITORY: 20,
            MonitorType.TEXT_PAYLOAD: 15,
            MonitorType.FILE_CONTENT: 10,
        }[event.monitor_type]
        decoy = 20 if decoy_type == "database_record" else 15 if decoy_type == "secret" else 10
        score = (
            event.confidence * 35 + monitor + decoy + placement_priority * 15 + min(10, count * 2)
        )
        if score >= 90:
            return Severity.CRITICAL
        if score >= 70:
            return Severity.HIGH
        if score >= 45:
            return Severity.MEDIUM
        if score >= 25:
            return Severity.LOW
        return Severity.INFO
