# Purpose: persist and retrieve engine artifacts as JSON blobs, scoped by organization.
# Responsibilities: isolate all SQLAlchemy access behind typed methods that speak in domain models
#   and always filter/stamp by organization_id, so no read or write path is globally scoped.
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


class ArtifactTooLargeError(Exception):
    """Raised when a serialized artifact exceeds the configured maximum size."""


class ArtifactRepository:
    """Organization-scoped persistence gateway for the pipeline artifacts."""

    def __init__(self, session: Session, max_artifact_bytes: int | None = None) -> None:
        self._session = session
        self._max_artifact_bytes = max_artifact_bytes

    def _guard_size(self, serialized: str) -> str:
        if self._max_artifact_bytes is not None and len(serialized.encode("utf-8")) > (
            self._max_artifact_bytes
        ):
            raise ArtifactTooLargeError("serialized artifact exceeds the maximum size")
        return serialized

    # -- repositories ---------------------------------------------------------------------------

    def add_repository(
        self,
        organization_id: UUID,
        name: str,
        root_path: str,
        profile: RepositoryIntelligenceProfile,
    ) -> UUID:
        record = RepositoryRecord(
            organization_id=organization_id,
            name=name,
            root_path=root_path,
            profile=self._guard_size(profile.model_dump_json()),
        )
        self._session.add(record)
        self._session.flush()
        return record.id

    def get_profile(
        self, organization_id: UUID, repository_id: UUID
    ) -> RepositoryIntelligenceProfile | None:
        record = self._session.get(RepositoryRecord, repository_id)
        if record is None or record.organization_id != organization_id:
            return None
        return RepositoryIntelligenceProfile.model_validate_json(record.profile)

    def latest_repository_at_path(
        self, organization_id: UUID, root_path: str
    ) -> tuple[UUID, RepositoryIntelligenceProfile] | None:
        record = self._session.scalars(
            select(RepositoryRecord)
            .where(
                RepositoryRecord.organization_id == organization_id,
                RepositoryRecord.root_path == root_path,
            )
            .order_by(RepositoryRecord.created_at.desc())
        ).first()
        if record is None:
            return None
        return record.id, RepositoryIntelligenceProfile.model_validate_json(record.profile)

    # -- context / placements / decoys --------------------------------------------------------

    def add_context(
        self, organization_id: UUID, repository_id: UUID, context: OrganizationContextProfile
    ) -> UUID:
        record = ContextProfileRecord(
            organization_id=organization_id,
            repository_id=repository_id,
            data=self._guard_size(context.model_dump_json()),
        )
        self._session.add(record)
        self._session.flush()
        return record.id

    def latest_context(
        self, organization_id: UUID, repository_id: UUID
    ) -> OrganizationContextProfile | None:
        record = self._latest(ContextProfileRecord, organization_id, repository_id)
        if record is None:
            return None
        return OrganizationContextProfile.model_validate_json(record.data)

    def add_placement_plan(
        self, organization_id: UUID, repository_id: UUID, plan: PlacementPlan
    ) -> UUID:
        record = PlacementPlanRecord(
            organization_id=organization_id,
            repository_id=repository_id,
            data=self._guard_size(plan.model_dump_json()),
        )
        self._session.add(record)
        self._session.flush()
        return record.id

    def latest_placement_plan(
        self, organization_id: UUID, repository_id: UUID
    ) -> PlacementPlan | None:
        record = self._latest(PlacementPlanRecord, organization_id, repository_id)
        if record is None:
            return None
        return PlacementPlan.model_validate_json(record.data)

    def add_decoy_plan(
        self, organization_id: UUID, repository_id: UUID, plan: DecoyGenerationPlan
    ) -> UUID:
        record = DecoyPlanRecord(
            organization_id=organization_id,
            repository_id=repository_id,
            data=self._guard_size(plan.model_dump_json()),
        )
        self._session.add(record)
        self._session.flush()
        return record.id

    def get_decoy_plan(
        self, organization_id: UUID, decoy_plan_id: UUID
    ) -> tuple[UUID, DecoyGenerationPlan] | None:
        record = self._session.get(DecoyPlanRecord, decoy_plan_id)
        if record is None or record.organization_id != organization_id:
            return None
        return record.repository_id, DecoyGenerationPlan.model_validate_json(record.data)

    def latest_decoy_plan(
        self, organization_id: UUID, repository_id: UUID
    ) -> tuple[UUID, DecoyGenerationPlan] | None:
        record = self._latest(DecoyPlanRecord, organization_id, repository_id)
        if record is None:
            return None
        return record.id, DecoyGenerationPlan.model_validate_json(record.data)

    # -- validation reports -------------------------------------------------------------------

    def add_validation_report(
        self, organization_id: UUID, decoy_plan_id: UUID, report: BelievabilitySafetyReport
    ) -> None:
        self._session.add(
            ValidationReportRecord(
                organization_id=organization_id,
                decoy_plan_id=decoy_plan_id,
                decoy_id=report.decoy_id,
                data=self._guard_size(report.model_dump_json()),
            )
        )
        self._session.flush()

    def reports_for_decoy_plan(
        self, organization_id: UUID, decoy_plan_id: UUID
    ) -> tuple[BelievabilitySafetyReport, ...]:
        rows = self._session.scalars(
            select(ValidationReportRecord).where(
                ValidationReportRecord.organization_id == organization_id,
                ValidationReportRecord.decoy_plan_id == decoy_plan_id,
            )
        ).all()
        return tuple(BelievabilitySafetyReport.model_validate_json(row.data) for row in rows)

    # -- detection events ---------------------------------------------------------------------

    def add_detection_event(self, organization_id: UUID, event: RawDetectionEvent) -> None:
        self._session.merge(
            DetectionEventRecord(
                id=event.event_id,
                organization_id=organization_id,
                trace_identifier=event.trace_identifier,
                decoy_id=event.decoy_id,
                data=self._guard_size(event.model_dump_json()),
            )
        )
        self._session.flush()

    def detection_events_for_decoys(
        self, organization_id: UUID, decoy_ids: set[UUID]
    ) -> tuple[RawDetectionEvent, ...]:
        if not decoy_ids:
            return ()
        rows = self._session.scalars(
            select(DetectionEventRecord)
            .where(
                DetectionEventRecord.organization_id == organization_id,
                DetectionEventRecord.decoy_id.in_(decoy_ids),
            )
            .order_by(DetectionEventRecord.created_at)
        ).all()
        return tuple(RawDetectionEvent.model_validate_json(row.data) for row in rows)

    # -- alerts -------------------------------------------------------------------------------

    def add_alert(self, organization_id: UUID, alert: NormalizedAlert) -> None:
        self._session.merge(
            AlertRecord(
                id=alert.alert_id,
                organization_id=organization_id,
                trace_identifier=alert.trace_identifier,
                decoy_id=alert.decoy_id,
                data=self._guard_size(alert.model_dump_json()),
            )
        )
        self._session.flush()

    def alerts_for_organization(
        self, organization_id: UUID, limit: int | None = None
    ) -> tuple[NormalizedAlert, ...]:
        if limit is None:
            rows = self._session.scalars(
                select(AlertRecord)
                .where(AlertRecord.organization_id == organization_id)
                .order_by(AlertRecord.created_at)
            ).all()
            return tuple(NormalizedAlert.model_validate_json(row.data) for row in rows)
        # Bound the working set to the most recent alerts, returned chronologically.
        recent = self._session.scalars(
            select(AlertRecord)
            .where(AlertRecord.organization_id == organization_id)
            .order_by(AlertRecord.created_at.desc())
            .limit(limit)
        ).all()
        return tuple(
            NormalizedAlert.model_validate_json(row.data) for row in reversed(recent)
        )

    def alerts_for_decoys(
        self, organization_id: UUID, decoy_ids: set[UUID]
    ) -> tuple[NormalizedAlert, ...]:
        if not decoy_ids:
            return ()
        rows = self._session.scalars(
            select(AlertRecord)
            .where(
                AlertRecord.organization_id == organization_id,
                AlertRecord.decoy_id.in_(decoy_ids),
            )
            .order_by(AlertRecord.created_at)
        ).all()
        return tuple(NormalizedAlert.model_validate_json(row.data) for row in rows)

    # -- incidents ----------------------------------------------------------------------------

    def upsert_incidents_for_organization(
        self, organization_id: UUID, incidents: tuple[ReconstructedIncident, ...]
    ) -> None:
        """Upsert this organization's incidents by id, without a global delete/reinsert.

        Only the incidents produced by reconstructing this organization's alerts are written;
        rows are merged by their deterministic id, and other organizations are never touched.
        """
        for incident in incidents:
            self._session.merge(
                IncidentRecord(
                    id=incident.incident_id,
                    organization_id=organization_id,
                    data=self._guard_size(incident.model_dump_json()),
                )
            )
        self._session.flush()

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

    # -- narratives ---------------------------------------------------------------------------

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
                data=self._guard_size(narrative.model_dump_json()),
            )
        )
        self._session.flush()

    def prune_narrative_revisions(
        self, organization_id: UUID, incident_id: UUID, keep: int
    ) -> None:
        """Retain only the newest ``keep`` narrative revisions for an incident."""
        if keep <= 0:
            return
        records = self._session.scalars(
            select(NarrativeRevisionRecord)
            .where(
                NarrativeRevisionRecord.organization_id == organization_id,
                NarrativeRevisionRecord.incident_id == incident_id,
            )
            .order_by(NarrativeRevisionRecord.revision_number.desc())
        ).all()
        for record in records[keep:]:
            self._session.delete(record)
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

    # -- maintenance --------------------------------------------------------------------------

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

    # -- internals ----------------------------------------------------------------------------

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

    def _latest(self, model: Any, organization_id: UUID, repository_id: UUID) -> Any:
        return self._session.scalars(
            select(model)
            .where(
                model.organization_id == organization_id,
                model.repository_id == repository_id,
            )
            .order_by(model.created_at.desc())
        ).first()
