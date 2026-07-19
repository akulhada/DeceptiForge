"""In-memory normalization, enrichment, and time-window deduplication of raw events."""

from uuid import NAMESPACE_URL, UUID, uuid5

from app.models.domain.operations import (
    AlertEvidence,
    MonitorHealthMetadata,
    NormalizedAlert,
    RawDetectionEvent,
    Severity,
    TripwireRegistryEntry,
)
from app.services.alerting.scoring import AlertingConfig, AlertSeverityScorer

_SEVERITY_RANK = {
    Severity.INFO: 0,
    Severity.LOW: 1,
    Severity.MEDIUM: 2,
    Severity.HIGH: 3,
    Severity.CRITICAL: 4,
}


def combine_alerts(existing: NormalizedAlert, candidate: NormalizedAlert) -> NormalizedAlert:
    """Merge a fresh single-event candidate into an existing alert for the same episode.

    Deterministic and commutative in the fields that matter under concurrency: event counts add,
    first/last seen widen, severity/confidence take the maximum, and evidence/event references stay
    bounded. Each accepted ingest is counted; genuine duplicate delivery is stopped upstream by the
    nonce replay guard (a replayed nonce is rejected before it ever reaches this merge), so the
    upsert never needs to guess whether an event is a retry. Used by the atomic upsert when two
    ingests target the same episode row.
    """
    evidence = (*existing.evidence, *candidate.evidence)[-5:]
    severity = max(
        existing.severity, candidate.severity, key=lambda level: _SEVERITY_RANK[level]
    )
    return existing.model_copy(
        update={
            "event_count": existing.event_count + candidate.event_count,
            "first_seen": min(existing.first_seen, candidate.first_seen),
            "last_seen": max(existing.last_seen, candidate.last_seen),
            "severity": severity,
            "confidence": max(existing.confidence, candidate.confidence),
            "evidence": evidence,
            "raw_event_ids": (*existing.raw_event_ids, *candidate.raw_event_ids)[-20:],
        }
    )


class AlertingPipeline:
    def __init__(
        self,
        scorer: AlertSeverityScorer | None = None,
        existing: tuple[NormalizedAlert, ...] = (),
    ) -> None:
        self._scorer = scorer or AlertSeverityScorer()
        # Seed prior alerts by their episode-specific identity. More than one alert may share a
        # deduplication key when the same tripwire is observed in separate time windows.
        self._alerts: dict[str, NormalizedAlert] = {
            str(alert.alert_id): alert for alert in existing
        }

    def ingest(
        self,
        event: RawDetectionEvent,
        tripwire: TripwireRegistryEntry | None,
        config: AlertingConfig | None = None,
        health: tuple[MonitorHealthMetadata, ...] = (),
        organization_id: UUID | None = None,
    ) -> NormalizedAlert | None:
        config = config or AlertingConfig()
        if not self._valid(event):
            return None
        entry = tripwire or self._fallback(event)
        key = self._key(event)
        existing = self._matching_alert(key, event, config)
        if existing and abs((event.timestamp - existing.last_seen).total_seconds()) <= (
            config.deduplication_window_seconds
        ):
            updated = self._update(existing, event, entry, config, health)
            self._alerts[str(updated.alert_id)] = updated
            return updated
        alert = self._create(event, entry, key, config, health, organization_id)
        self._alerts[str(alert.alert_id)] = alert
        return alert

    def alerts(self) -> tuple[NormalizedAlert, ...]:
        return tuple(
            sorted(self._alerts.values(), key=lambda alert: (alert.first_seen, str(alert.alert_id)))
        )

    def _matching_alert(
        self, key: str, event: RawDetectionEvent, config: AlertingConfig
    ) -> NormalizedAlert | None:
        """Find the closest previous alert for this surface within the deduplication window."""
        candidates = (
            alert for alert in self._alerts.values() if alert.deduplication_key == key
        )
        matching = (
            alert
            for alert in candidates
            if abs((event.timestamp - alert.last_seen).total_seconds())
            <= config.deduplication_window_seconds
        )
        return min(
            matching,
            key=lambda alert: abs((event.timestamp - alert.last_seen).total_seconds()),
            default=None,
        )

    @staticmethod
    def _valid(event: RawDetectionEvent) -> bool:
        return bool(
            event.trace_identifier and event.observed_value_excerpt and event.confidence >= 0.5
        )

    @staticmethod
    def _key(event: RawDetectionEvent) -> str:
        return ":".join(
            (
                event.trace_identifier,
                str(event.decoy_id),
                event.monitor_type.value,
                event.observed_location,
                event.source.value,
                event.detection_method.value,
            )
        )

    @staticmethod
    def _fallback(event: RawDetectionEvent) -> TripwireRegistryEntry:
        return TripwireRegistryEntry(
            trace_identifier=event.trace_identifier,
            decoy_id=event.decoy_id,
            placement_id=event.correlation_id,
            target_location=event.observed_location,
            template_id="unknown",
            decoy_type="unknown",
        )

    def _create(
        self,
        event: RawDetectionEvent,
        entry: TripwireRegistryEntry,
        key: str,
        config: AlertingConfig,
        health: tuple[MonitorHealthMetadata, ...],
        organization_id: UUID | None = None,
    ) -> NormalizedAlert:
        severity = self._scorer.severity(event, entry.decoy_type, 1.0, 1)
        # The deduplication key describes the detection surface; the time bucket distinguishes
        # separate episodes on that same surface so a later alert cannot overwrite the first row.
        # The organization is folded into the id so identities never collide across tenants.
        episode = int(event.timestamp.timestamp() // max(1, config.deduplication_window_seconds))
        return NormalizedAlert(
            alert_id=uuid5(NAMESPACE_URL, f"{organization_id}:{key}:{episode}"),
            trace_identifier=event.trace_identifier,
            decoy_id=event.decoy_id,
            severity=severity,
            title=f"Decoy trace observed in {event.monitor_type.value}",
            summary=f"Trace {event.trace_identifier} was observed at {event.observed_location}.",
            source_monitor=event.monitor_type,
            confidence=event.confidence,
            first_seen=event.timestamp,
            last_seen=event.timestamp,
            event_count=1,
            deduplication_key=key,
            episode_bucket=episode,
            affected_placement_id=entry.placement_id,
            affected_decoy_type=entry.decoy_type,
            evidence=(
                AlertEvidence(
                    excerpt=event.observed_value_excerpt,
                    digest=event.evidence_digest,
                    location=event.observed_location,
                ),
            ),
            raw_event_ids=(event.event_id,),
            recommended_actions=self._actions(event.monitor_type),
            correlation_id=event.correlation_id,
            false_positive_notes=self._health_notes(health),
            escalation_hints=self._hints(severity),
        )

    def _update(
        self,
        alert: NormalizedAlert,
        event: RawDetectionEvent,
        entry: TripwireRegistryEntry,
        config: AlertingConfig,
        health: tuple[MonitorHealthMetadata, ...],
    ) -> NormalizedAlert:
        count = alert.event_count + 1
        severity = self._scorer.severity(event, entry.decoy_type, 1.0, count)
        evidence = (
            *alert.evidence,
            AlertEvidence(
                excerpt=event.observed_value_excerpt,
                digest=event.evidence_digest,
                location=event.observed_location,
            ),
        )[-5:]
        return alert.model_copy(
            update={
                "first_seen": min(alert.first_seen, event.timestamp),
                "last_seen": max(alert.last_seen, event.timestamp),
                "event_count": count,
                "severity": severity,
                "confidence": max(alert.confidence, event.confidence),
                "evidence": evidence,
                "raw_event_ids": (*alert.raw_event_ids, event.event_id)[-20:],
                "false_positive_notes": self._health_notes(health),
            }
        )

    @staticmethod
    def _actions(monitor: str) -> tuple[str, ...]:
        return {
            "text_payload": (
                "Verify whether internal data was pasted into an AI tool.",
                "Review activity around the timestamp.",
            ),
            "repository": (
                "Inspect repository commit and file history.",
                "Review repository access permissions.",
            ),
            "database_payload": (
                "Inspect query and export logs.",
                "Review service-account activity.",
            ),
            "file_content": (
                "Review file owner and recent modifications.",
                "Check whether the file was copied or synced.",
            ),
        }[monitor]

    @staticmethod
    def _health_notes(health: tuple[MonitorHealthMetadata, ...]) -> tuple[str, ...]:
        return tuple(
            "Monitor health is degraded."
            for item in health
            if item.status.value in {"degraded", "failed"}
        )

    @staticmethod
    def _hints(severity: Severity) -> tuple[str, ...]:
        return (
            (
                "Escalate to security operations."
                if severity in {Severity.HIGH, Severity.CRITICAL}
                else "Review during normal triage."
            ),
        )
