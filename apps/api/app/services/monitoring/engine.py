"""Deterministic monitor registration and caller-driven payload scanning."""

from datetime import UTC, datetime
from uuid import NAMESPACE_URL, UUID, uuid5

from app.models.domain.decoy import BelievabilityDecision, BelievabilitySafetyReport, DecoyAsset
from app.models.domain.operations import (
    DetectionMethod,
    DetectionSource,
    MonitorHealthMetadata,
    MonitorHealthStatus,
    MonitorRegistration,
    MonitorRegistrationPlan,
    MonitorType,
    RawDetectionEvent,
    Severity,
    TripwireRegistryEntry,
)
from app.services.monitoring.matching import TraceMatcher
from app.services.monitoring.registry import TripwireRegistry


class MonitoringInstrumentationEngine:
    def __init__(
        self, registry: TripwireRegistry | None = None, matcher: TraceMatcher | None = None
    ) -> None:
        self._registry = registry or TripwireRegistry()
        self._matcher = matcher or TraceMatcher()
        self._seen_events: set[tuple[str, str, str]] = set()

    def register(
        self, assets: tuple[DecoyAsset, ...], reports: tuple[BelievabilitySafetyReport, ...]
    ) -> MonitorRegistrationPlan:
        reports_by_id = {report.decoy_id: report for report in reports}
        registrations: list[MonitorRegistration] = []
        rejected: list[UUID] = []
        for asset in assets:
            report = reports_by_id.get(asset.decoy_id)
            if report is None or report.decision is not BelievabilityDecision.ACCEPT:
                rejected.append(asset.decoy_id)
                continue
            entry = self._registry.register(
                TripwireRegistryEntry(
                    trace_identifier=asset.trigger_metadata.trace_identifier,
                    decoy_id=asset.decoy_id,
                    placement_id=asset.target_placement_id,
                    target_location=asset.target_location,
                    template_id=asset.template_id.value,
                    decoy_type=asset.decoy_type.value,
                )
            )
            registrations.extend(
                MonitorRegistration(
                    monitor_type=monitor_type,
                    trace_identifier=entry.trace_identifier,
                    target_location=entry.target_location,
                    status=MonitorHealthStatus.ACTIVE,
                )
                for monitor_type in self._monitor_types(entry)
            )
        return MonitorRegistrationPlan(
            registrations=tuple(registrations), rejected_decoy_ids=tuple(rejected)
        )

    def scan_text(
        self, text: str, location: str, monitor_type: MonitorType = MonitorType.TEXT_PAYLOAD
    ) -> RawDetectionEvent | None:
        match = self._matcher.match(text, self._registry.active())
        if match is None:
            return None
        entry, confidence, excerpt = match
        digest = self._matcher.digest(text)
        key = (entry.trace_identifier, location, digest)
        if key in self._seen_events:
            return None
        self._seen_events.add(key)
        event_id = uuid5(NAMESPACE_URL, ":".join(key))
        return RawDetectionEvent(
            event_id=event_id,
            trace_identifier=entry.trace_identifier,
            decoy_id=entry.decoy_id,
            monitor_type=monitor_type,
            observed_location=location,
            observed_value_excerpt=excerpt,
            timestamp=datetime.now(UTC),
            source=self._source(monitor_type),
            confidence=confidence,
            severity_suggestion=Severity.HIGH if confidence == 1 else Severity.MEDIUM,
            evidence_digest=digest,
            detection_method=DetectionMethod.CONTENT_ACCESS,
            correlation_id=uuid5(NAMESPACE_URL, f"{entry.decoy_id}:{entry.trace_identifier}"),
        )

    def scan_file_content(self, path: str, content: str) -> RawDetectionEvent | None:
        return self.scan_text(content, path, MonitorType.FILE_CONTENT)

    def scan_repository_file(self, path: str, content: str) -> RawDetectionEvent | None:
        return self.scan_text(content, path, MonitorType.REPOSITORY)

    def scan_database_payload(self, location: str, payload: str) -> RawDetectionEvent | None:
        return self.scan_text(payload, location, MonitorType.DATABASE_PAYLOAD)

    def disable(self, trace_identifier: str) -> bool:
        return self._registry.disable(trace_identifier)

    def active_tripwires(self) -> tuple[TripwireRegistryEntry, ...]:
        return self._registry.active()

    @staticmethod
    def health() -> tuple[MonitorHealthMetadata, ...]:
        return tuple(
            MonitorHealthMetadata(
                monitor_type=monitor_type,
                status=MonitorHealthStatus.ACTIVE,
                detail="In-memory scan interface is available; no external listener is active.",
            )
            for monitor_type in MonitorType
        )

    @staticmethod
    def _monitor_types(entry: TripwireRegistryEntry) -> tuple[MonitorType, ...]:
        types = [MonitorType.TEXT_PAYLOAD, MonitorType.FILE_CONTENT, MonitorType.REPOSITORY]
        if entry.decoy_type == "database_record":
            types.append(MonitorType.DATABASE_PAYLOAD)
        return tuple(types)

    @staticmethod
    def _source(monitor_type: MonitorType) -> DetectionSource:
        return {
            MonitorType.FILE_CONTENT: DetectionSource.DOCUMENT,
            MonitorType.REPOSITORY: DetectionSource.REPOSITORY,
            MonitorType.DATABASE_PAYLOAD: DetectionSource.DATABASE,
            MonitorType.TEXT_PAYLOAD: DetectionSource.SYSTEM,
        }[monitor_type]
