# Purpose: persist and retrieve engine artifacts as JSON blobs.
# Responsibilities: isolate all SQLAlchemy access for the vertical slice behind typed methods that
#   speak in domain models; callers never touch records or serialization directly.
# Dependencies: SQLAlchemy session and the persistence records.
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.domain.decoy import BelievabilitySafetyReport, DecoyGenerationPlan
from app.models.domain.intelligence import (
    OrganizationContextProfile,
    PlacementPlan,
    RepositoryIntelligenceProfile,
)
from app.models.domain.narrative import IncidentNarrative
from app.models.domain.operations import (
    NormalizedAlert,
    RawDetectionEvent,
    ReconstructedIncident,
)
from app.models.records import (
    AlertRecord,
    ContextProfileRecord,
    DecoyPlanRecord,
    DetectionEventRecord,
    IncidentRecord,
    NarrativeRevisionRecord,
    PlacementPlanRecord,
    RepositoryRecord,
    ValidationReportRecord,
)


class ArtifactRepository:
    """Typed persistence gateway for the pipeline artifacts."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add_repository(
        self, name: str, root_path: str, profile: RepositoryIntelligenceProfile
    ) -> UUID:
        record = RepositoryRecord(name=name, root_path=root_path, profile=profile.model_dump_json())
        self._session.add(record)
        self._session.flush()
        return record.id

    def get_profile(self, repository_id: UUID) -> RepositoryIntelligenceProfile | None:
        record = self._session.get(RepositoryRecord, repository_id)
        if record is None:
            return None
        return RepositoryIntelligenceProfile.model_validate_json(record.profile)

    def add_context(self, repository_id: UUID, context: OrganizationContextProfile) -> UUID:
        record = ContextProfileRecord(repository_id=repository_id, data=context.model_dump_json())
        self._session.add(record)
        self._session.flush()
        return record.id

    def latest_context(self, repository_id: UUID) -> OrganizationContextProfile | None:
        record = self._latest(ContextProfileRecord, repository_id)
        if record is None:
            return None
        return OrganizationContextProfile.model_validate_json(record.data)

    def add_placement_plan(self, repository_id: UUID, plan: PlacementPlan) -> UUID:
        record = PlacementPlanRecord(repository_id=repository_id, data=plan.model_dump_json())
        self._session.add(record)
        self._session.flush()
        return record.id

    def latest_placement_plan(self, repository_id: UUID) -> PlacementPlan | None:
        record = self._latest(PlacementPlanRecord, repository_id)
        if record is None:
            return None
        return PlacementPlan.model_validate_json(record.data)

    def add_decoy_plan(self, repository_id: UUID, plan: DecoyGenerationPlan) -> UUID:
        record = DecoyPlanRecord(repository_id=repository_id, data=plan.model_dump_json())
        self._session.add(record)
        self._session.flush()
        return record.id

    def get_decoy_plan(self, decoy_plan_id: UUID) -> tuple[UUID, DecoyGenerationPlan] | None:
        record = self._session.get(DecoyPlanRecord, decoy_plan_id)
        if record is None:
            return None
        return record.repository_id, DecoyGenerationPlan.model_validate_json(record.data)

    def latest_repository(self) -> tuple[UUID, RepositoryIntelligenceProfile] | None:
        record = self._session.scalars(
            select(RepositoryRecord).order_by(RepositoryRecord.created_at.desc())
        ).first()
        if record is None:
            return None
        return record.id, RepositoryIntelligenceProfile.model_validate_json(record.profile)

    def latest_repository_at_path(
        self, root_path: str
    ) -> tuple[UUID, RepositoryIntelligenceProfile] | None:
        record = self._session.scalars(
            select(RepositoryRecord)
            .where(RepositoryRecord.root_path == root_path)
            .order_by(RepositoryRecord.created_at.desc())
        ).first()
        if record is None:
            return None
        return record.id, RepositoryIntelligenceProfile.model_validate_json(record.profile)

    def latest_decoy_plan(self, repository_id: UUID) -> tuple[UUID, DecoyGenerationPlan] | None:
        record = self._latest(DecoyPlanRecord, repository_id)
        if record is None:
            return None
        return record.id, DecoyGenerationPlan.model_validate_json(record.data)

    def all_detection_events(self) -> tuple[RawDetectionEvent, ...]:
        rows = self._session.scalars(
            select(DetectionEventRecord).order_by(DetectionEventRecord.created_at)
        ).all()
        return tuple(RawDetectionEvent.model_validate_json(row.data) for row in rows)

    def detection_events_for_decoys(self, decoy_ids: set[UUID]) -> tuple[RawDetectionEvent, ...]:
        if not decoy_ids:
            return ()
        rows = self._session.scalars(
            select(DetectionEventRecord)
            .where(DetectionEventRecord.decoy_id.in_(decoy_ids))
            .order_by(DetectionEventRecord.created_at)
        ).all()
        return tuple(RawDetectionEvent.model_validate_json(row.data) for row in rows)

    def add_validation_report(self, decoy_plan_id: UUID, report: BelievabilitySafetyReport) -> None:
        self._session.add(
            ValidationReportRecord(
                decoy_plan_id=decoy_plan_id,
                decoy_id=report.decoy_id,
                data=report.model_dump_json(),
            )
        )
        self._session.flush()

    def reports_for_decoy_plan(self, decoy_plan_id: UUID) -> tuple[BelievabilitySafetyReport, ...]:
        rows = self._session.scalars(
            select(ValidationReportRecord).where(
                ValidationReportRecord.decoy_plan_id == decoy_plan_id
            )
        ).all()
        return tuple(BelievabilitySafetyReport.model_validate_json(row.data) for row in rows)

    def add_detection_event(self, event: RawDetectionEvent) -> None:
        self._session.merge(
            DetectionEventRecord(
                id=event.event_id,
                trace_identifier=event.trace_identifier,
                decoy_id=event.decoy_id,
                data=event.model_dump_json(),
            )
        )
        self._session.flush()

    def add_alert(self, alert: NormalizedAlert) -> None:
        self._session.merge(
            AlertRecord(
                id=alert.alert_id,
                trace_identifier=alert.trace_identifier,
                decoy_id=alert.decoy_id,
                data=alert.model_dump_json(),
            )
        )
        self._session.flush()

    def all_alerts(self) -> tuple[NormalizedAlert, ...]:
        rows = self._session.scalars(select(AlertRecord).order_by(AlertRecord.created_at)).all()
        return tuple(NormalizedAlert.model_validate_json(row.data) for row in rows)

    def alerts_for_organization(self, organization_id: UUID) -> tuple[NormalizedAlert, ...]:
        rows = self._session.scalars(
            select(AlertRecord)
            .where(AlertRecord.organization_id == organization_id)
            .order_by(AlertRecord.created_at)
        ).all()
        return tuple(NormalizedAlert.model_validate_json(row.data) for row in rows)

    def alerts_for_decoys(self, decoy_ids: set[UUID]) -> tuple[NormalizedAlert, ...]:
        if not decoy_ids:
            return ()
        rows = self._session.scalars(
            select(AlertRecord)
            .where(AlertRecord.decoy_id.in_(decoy_ids))
            .order_by(AlertRecord.created_at)
        ).all()
        return tuple(NormalizedAlert.model_validate_json(row.data) for row in rows)

    def replace_incidents(self, incidents: tuple[ReconstructedIncident, ...]) -> None:
        self._session.execute(delete(IncidentRecord))
        for incident in incidents:
            self._session.add(
                IncidentRecord(id=incident.incident_id, data=incident.model_dump_json())
            )
        self._session.flush()

    def reset_all(self) -> None:
        """Delete every stored artifact. Demo-only; used by the demo reset endpoint."""
        for record in (
            NarrativeRevisionRecord,
            IncidentRecord,
            AlertRecord,
            DetectionEventRecord,
            ValidationReportRecord,
            DecoyPlanRecord,
            PlacementPlanRecord,
            ContextProfileRecord,
            RepositoryRecord,
        ):
            self._session.execute(delete(record))
        self._session.flush()

    def all_incidents(self) -> tuple[ReconstructedIncident, ...]:
        rows = self._session.scalars(
            select(IncidentRecord).order_by(IncidentRecord.created_at)
        ).all()
        return tuple(ReconstructedIncident.model_validate_json(row.data) for row in rows)

    def incidents_for_organization(
        self, organization_id: UUID
    ) -> tuple[ReconstructedIncident, ...]:
        rows = self._session.scalars(
            select(IncidentRecord)
            .where(IncidentRecord.organization_id == organization_id)
            .order_by(IncidentRecord.created_at)
        ).all()
        return tuple(ReconstructedIncident.model_validate_json(row.data) for row in rows)

    def get_incident(
        self, organization_id: UUID, incident_id: UUID
    ) -> ReconstructedIncident | None:
        record = self._session.get(IncidentRecord, incident_id)
        if record is None or record.organization_id != organization_id:
            return None
        return ReconstructedIncident.model_validate_json(record.data)

    def next_revision_number(self, organization_id: UUID, incident_id: UUID) -> int:
        latest = self._latest_revision_record(organization_id, incident_id)
        return 1 if latest is None else latest.revision_number + 1

    def add_narrative_revision(self, narrative: IncidentNarrative) -> None:
        self._session.add(
            NarrativeRevisionRecord(
                organization_id=narrative.organization_id,
                incident_id=narrative.incident_id,
                revision_number=narrative.revision_number,
                context_hash=narrative.source_context_hash,
                status=narrative.status.value,
                data=narrative.model_dump_json(),
            )
        )
        self._session.flush()

    def latest_narrative(
        self, organization_id: UUID, incident_id: UUID
    ) -> IncidentNarrative | None:
        record = self._latest_revision_record(organization_id, incident_id)
        if record is None:
            return None
        return IncidentNarrative.model_validate_json(record.data)

    def list_narratives(
        self, organization_id: UUID, incident_id: UUID
    ) -> tuple[IncidentNarrative, ...]:
        rows = self._session.scalars(
            select(NarrativeRevisionRecord)
            .where(
                NarrativeRevisionRecord.organization_id == organization_id,
                NarrativeRevisionRecord.incident_id == incident_id,
            )
            .order_by(NarrativeRevisionRecord.revision_number)
        ).all()
        return tuple(IncidentNarrative.model_validate_json(row.data) for row in rows)

    def _latest_revision_record(
        self, organization_id: UUID, incident_id: UUID
    ) -> NarrativeRevisionRecord | None:
        return self._session.scalars(
            select(NarrativeRevisionRecord)
            .where(
                NarrativeRevisionRecord.organization_id == organization_id,
                NarrativeRevisionRecord.incident_id == incident_id,
            )
            .order_by(NarrativeRevisionRecord.revision_number.desc())
        ).first()

    def _latest(self, model: Any, repository_id: UUID) -> Any:
        return self._session.scalars(
            select(model)
            .where(model.repository_id == repository_id)
            .order_by(model.created_at.desc())
        ).first()
