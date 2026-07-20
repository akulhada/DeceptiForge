# Purpose: persist and retrieve engine artifacts as JSON blobs, scoped by organization.
# Responsibilities: isolate all SQLAlchemy access behind typed methods that speak in domain models
#   and always filter/stamp by organization_id, so no read or write path is globally scoped.
# Dependencies: SQLAlchemy session and the persistence records.
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID

from sqlalchemy import CursorResult, delete, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.domain.decoy import BelievabilitySafetyReport, DecoyGenerationPlan
from app.models.domain.intelligence import (
    OrganizationContextProfile,
    PlacementPlan,
    RepositoryIntelligenceProfile,
)
from app.models.domain.narrative import IncidentNarrative
from app.models.domain.operations import (
    IncidentLifecycle,
    NormalizedAlert,
    RawDetectionEvent,
    ReconstructedIncident,
)
from app.models.records import (
    AlertRecord,
    ApiKeyRecord,
    ContextProfileRecord,
    DecoyPlanRecord,
    DetectionEventRecord,
    IncidentRecord,
    NarrativeRevisionRecord,
    PlacementPlanRecord,
    ReconstructionJobRecord,
    RepositoryRecord,
    ValidationReportRecord,
)
from app.services.alerting.engine import combine_alerts
from app.services.encryption import EncryptionProvider, get_encryption_provider


class ArtifactTooLargeError(Exception):
    """Raised when a serialized artifact exceeds the configured maximum size."""


class ArtifactRepository:
    """Organization-scoped persistence gateway for the pipeline artifacts."""

    def __init__(
        self,
        session: Session,
        max_artifact_bytes: int | None = None,
        encryption: EncryptionProvider | None = None,
    ) -> None:
        self._session = session
        self._max_artifact_bytes = max_artifact_bytes
        # Evidence-bearing blobs (alerts, detection events, incidents) are encrypted at rest.
        self._encryption = encryption or get_encryption_provider()

    def _guard_size(self, serialized: str) -> str:
        if self._max_artifact_bytes is not None and len(serialized.encode("utf-8")) > (
            self._max_artifact_bytes
        ):
            raise ArtifactTooLargeError("serialized artifact exceeds the maximum size")
        return serialized

    def _seal(self, serialized: str) -> str:
        """Encrypt an evidence-bearing blob before persistence (records the key version)."""
        return self._encryption.encrypt(serialized)

    def _unseal(self, stored: str) -> str:
        """Decrypt an evidence blob; tolerate legacy plaintext JSON rows from before encryption."""
        if stored.startswith("{"):
            return stored
        return self._encryption.decrypt(stored)

    def _decode_alerts(self, rows: Any) -> tuple[NormalizedAlert, ...]:
        return tuple(NormalizedAlert.model_validate_json(self._unseal(row.data)) for row in rows)

    def _decode_incidents(self, rows: Any) -> tuple[ReconstructedIncident, ...]:
        return tuple(
            ReconstructedIncident.model_validate_json(self._unseal(row.data)) for row in rows
        )

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

    def repositories_for_organization(
        self, organization_id: UUID
    ) -> tuple[tuple[UUID, str, RepositoryIntelligenceProfile], ...]:
        rows = self._session.scalars(
            select(RepositoryRecord)
            .where(RepositoryRecord.organization_id == organization_id)
            .order_by(RepositoryRecord.created_at.desc())
        ).all()
        return tuple(
            (row.id, row.name, RepositoryIntelligenceProfile.model_validate_json(row.profile))
            for row in rows
        )

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
                data=self._seal(self._guard_size(event.model_dump_json())),
            )
        )
        self._session.flush()

    def detection_events_for_organization(
        self, organization_id: UUID
    ) -> tuple[RawDetectionEvent, ...]:
        rows = self._session.scalars(
            select(DetectionEventRecord)
            .where(DetectionEventRecord.organization_id == organization_id)
            .order_by(DetectionEventRecord.created_at)
        ).all()
        return tuple(RawDetectionEvent.model_validate_json(self._unseal(row.data)) for row in rows)

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
        return tuple(RawDetectionEvent.model_validate_json(self._unseal(row.data)) for row in rows)

    # -- alerts -------------------------------------------------------------------------------

    def _alert_record(self, organization_id: UUID, alert: NormalizedAlert) -> AlertRecord:
        return AlertRecord(
            id=alert.alert_id,
            organization_id=organization_id,
            trace_identifier=alert.trace_identifier,
            decoy_id=alert.decoy_id,
            event_count=alert.event_count,
            episode_bucket=alert.episode_bucket,
            affected_placement_id=alert.affected_placement_id,
            correlation_id=alert.correlation_id,
            deduplication_key=alert.deduplication_key,
            first_seen=alert.first_seen,
            last_seen=alert.last_seen,
            data=self._seal(self._guard_size(alert.model_dump_json())),
        )

    def add_alert(self, organization_id: UUID, alert: NormalizedAlert) -> None:
        self._session.merge(self._alert_record(organization_id, alert))
        self._session.flush()

    def upsert_alert_atomic(
        self, organization_id: UUID, candidate: NormalizedAlert
    ) -> NormalizedAlert:
        """Atomically insert a fresh episode alert or merge into the existing one.

        Two concurrent duplicate ingests target the same episode identity. The first insert wins; a
        conflicting insert is caught at the database boundary (unique constraint), and the loser
        locks the existing row (``FOR UPDATE`` on PostgreSQL) and merges — so ``event_count``,
        ``first_seen``, and ``last_seen`` stay correct with no lost update and no error surfaced to
        the client. Reprocessing the same event is idempotent. Never crosses organizations.
        """
        try:
            with self._session.begin_nested():
                self._session.add(self._alert_record(organization_id, candidate))
            return candidate
        except IntegrityError:
            row = self._session.execute(
                select(AlertRecord)
                .where(AlertRecord.id == candidate.alert_id)
                .with_for_update()
            ).scalar_one()
            existing = NormalizedAlert.model_validate_json(self._unseal(row.data))
            merged = combine_alerts(existing, candidate)
            row.event_count = merged.event_count
            row.first_seen = merged.first_seen
            row.last_seen = merged.last_seen
            row.data = self._seal(self._guard_size(merged.model_dump_json()))
            self._session.flush()
            return merged

    def related_alerts(
        self,
        organization_id: UUID,
        *,
        trace_identifier: str,
        decoy_id: UUID,
        affected_placement_id: UUID | None,
        correlation_id: UUID | None,
        window_start: datetime,
        window_end: datetime,
        limit: int = 1000,
    ) -> tuple[NormalizedAlert, ...]:
        """Return alerts sharing a strong key with the trigger within the time window.

        Uses the indexed correlation columns so reconstruction never scans the whole alert table.
        """
        key_match = [
            AlertRecord.trace_identifier == trace_identifier,
            AlertRecord.decoy_id == decoy_id,
        ]
        if affected_placement_id is not None:
            key_match.append(AlertRecord.affected_placement_id == affected_placement_id)
        if correlation_id is not None:
            key_match.append(AlertRecord.correlation_id == correlation_id)
        rows = self._session.scalars(
            select(AlertRecord)
            .where(
                AlertRecord.organization_id == organization_id,
                or_(*key_match),
                # Overlap the correlation window: the alert's activity must intersect [start, end].
                or_(AlertRecord.last_seen.is_(None), AlertRecord.last_seen >= window_start),
                or_(AlertRecord.first_seen.is_(None), AlertRecord.first_seen <= window_end),
            )
            .order_by(AlertRecord.created_at.desc())
            .limit(limit)
        ).all()
        return self._decode_alerts(reversed(rows))

    # -- reconstruction work queue ------------------------------------------------------------

    def enqueue_reconstruction(
        self, organization_id: UUID, alert: NormalizedAlert, window_seconds: int
    ) -> UUID:
        """Append a reconstruction job for the alert's correlation neighborhood; return promptly."""
        record = ReconstructionJobRecord(
            organization_id=organization_id,
            status="pending",
            trace_identifier=alert.trace_identifier,
            decoy_id=alert.decoy_id,
            affected_placement_id=alert.affected_placement_id,
            correlation_id=alert.correlation_id,
            window_start=alert.first_seen - timedelta(seconds=window_seconds),
            window_end=alert.last_seen + timedelta(seconds=window_seconds),
        )
        self._session.add(record)
        self._session.flush()
        return record.id

    def claim_reconstruction_jobs(
        self, limit: int, organization_id: UUID | None = None
    ) -> tuple[ReconstructionJobRecord, ...]:
        """Atomically claim up to ``limit`` pending jobs so concurrent workers never double-process.

        Each candidate is claimed with a compare-and-set on status; only the worker whose UPDATE
        changes a row owns it. This is portable across PostgreSQL and SQLite.
        """
        query = select(ReconstructionJobRecord.id).where(
            ReconstructionJobRecord.status == "pending"
        )
        if organization_id is not None:
            query = query.where(ReconstructionJobRecord.organization_id == organization_id)
        candidate_ids = self._session.scalars(
            query.order_by(ReconstructionJobRecord.created_at).limit(limit)
        ).all()
        claimed: list[ReconstructionJobRecord] = []
        for job_id in candidate_ids:
            result = self._session.execute(
                update(ReconstructionJobRecord)
                .where(
                    ReconstructionJobRecord.id == job_id,
                    ReconstructionJobRecord.status == "pending",
                )
                .values(status="claimed")
            )
            if cast("CursorResult[Any]", result).rowcount == 1:
                record = self._session.get(ReconstructionJobRecord, job_id)
                if record is not None:
                    record.attempts += 1
                    claimed.append(record)
        self._session.flush()
        return tuple(claimed)

    def complete_reconstruction_job(self, job_id: UUID, *, ok: bool) -> None:
        record = self._session.get(ReconstructionJobRecord, job_id)
        if record is None:
            return
        record.status = "done" if ok else "failed"
        record.processed_at = datetime.now(UTC)
        self._session.flush()

    def pending_reconstruction_count(self, organization_id: UUID | None = None) -> int:
        query = select(ReconstructionJobRecord).where(
            ReconstructionJobRecord.status == "pending"
        )
        if organization_id is not None:
            query = query.where(ReconstructionJobRecord.organization_id == organization_id)
        return len(self._session.scalars(query).all())

    def alerts_for_organization(
        self, organization_id: UUID, limit: int | None = None
    ) -> tuple[NormalizedAlert, ...]:
        if limit is None:
            rows = self._session.scalars(
                select(AlertRecord)
                .where(AlertRecord.organization_id == organization_id)
                .order_by(AlertRecord.created_at)
            ).all()
            return self._decode_alerts(rows)
        # Bound the working set to the most recent alerts, returned chronologically.
        recent = self._session.scalars(
            select(AlertRecord)
            .where(AlertRecord.organization_id == organization_id)
            .order_by(AlertRecord.created_at.desc())
            .limit(limit)
        ).all()
        return self._decode_alerts(reversed(recent))

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
        return self._decode_alerts(rows)

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
                    status=incident.lifecycle.value,
                    last_seen=incident.last_seen,
                    data=self._seal(self._guard_size(incident.model_dump_json())),
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
        return self._decode_incidents(rows)

    def retire_stale_incidents(
        self, organization_id: UUID, now: datetime, stale_after_seconds: int
    ) -> int:
        """Mark this organization's incidents stale when not updated within the window.

        Non-destructive: incidents are re-tagged (lifecycle=stale), never deleted, and other
        organizations are untouched.
        """
        cutoff = now - timedelta(seconds=stale_after_seconds)
        retired = 0
        for incident in self.incidents_for_organization(organization_id):
            if incident.lifecycle is IncidentLifecycle.STALE or incident.last_seen >= cutoff:
                continue
            updated = incident.model_copy(
                update={"lifecycle": IncidentLifecycle.STALE, "updated_at": now}
            )
            self._session.merge(
                IncidentRecord(
                    id=updated.incident_id,
                    organization_id=organization_id,
                    status=updated.lifecycle.value,
                    last_seen=updated.last_seen,
                    data=self._seal(self._guard_size(updated.model_dump_json())),
                )
            )
            retired += 1
        self._session.flush()
        return retired

    def get_incident(
        self, organization_id: UUID, incident_id: UUID
    ) -> ReconstructedIncident | None:
        record = self._session.get(IncidentRecord, incident_id)
        if record is None or record.organization_id != organization_id:
            return None
        return ReconstructedIncident.model_validate_json(self._unseal(record.data))

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

    # -- retention / lifecycle ----------------------------------------------------------------

    def _batched_delete(self, model: Any, id_column: Any, condition: Any, batch: int) -> int:
        """Delete rows matching ``condition`` in bounded batches; return the total removed."""
        total = 0
        while True:
            ids = self._session.scalars(select(id_column).where(condition).limit(batch)).all()
            if not ids:
                break
            self._session.execute(delete(model).where(id_column.in_(ids)))
            self._session.flush()
            total += len(ids)
            if len(ids) < batch:
                break
        return total

    def purge_detection_events(self, cutoff: datetime, batch: int = 500) -> int:
        return self._batched_delete(
            DetectionEventRecord,
            DetectionEventRecord.id,
            DetectionEventRecord.created_at < cutoff,
            batch,
        )

    def purge_alerts(self, cutoff: datetime, batch: int = 500) -> int:
        return self._batched_delete(
            AlertRecord, AlertRecord.id, AlertRecord.created_at < cutoff, batch
        )

    def purge_reconstruction_jobs(self, cutoff: datetime, batch: int = 500) -> int:
        return self._batched_delete(
            ReconstructionJobRecord,
            ReconstructionJobRecord.id,
            (ReconstructionJobRecord.status.in_(("done", "failed")))
            & (ReconstructionJobRecord.created_at < cutoff),
            batch,
        )

    def purge_agent_activity_events(self, cutoff: datetime, batch: int = 500) -> int:
        """Delete raw minimized agent activity events older than the cutoff. Scope violations and
        session summaries are retained separately (longer) so incident evidence outlives raw
        activity."""
        from app.models.records import AgentActivityEventRecord

        return self._batched_delete(
            AgentActivityEventRecord,
            AgentActivityEventRecord.id,
            AgentActivityEventRecord.created_at < cutoff,
            batch,
        )

    def purge_expired_api_keys(self, now: datetime, cutoff: datetime, batch: int = 500) -> int:
        """Delete keys that are revoked or expired and older than the retention cutoff."""
        return self._batched_delete(
            ApiKeyRecord,
            ApiKeyRecord.id,
            (ApiKeyRecord.created_at < cutoff)
            & (
                (ApiKeyRecord.status == "revoked")
                | ((ApiKeyRecord.expires_at.is_not(None)) & (ApiKeyRecord.expires_at < now))
            ),
            batch,
        )

    def prune_all_narrative_revisions(self, keep: int) -> int:
        """Keep only the newest ``keep`` revisions per (organization, incident); return pruned."""
        if keep <= 0:
            return 0
        pairs = self._session.execute(
            select(
                NarrativeRevisionRecord.organization_id, NarrativeRevisionRecord.incident_id
            ).distinct()
        ).all()
        pruned = 0
        for organization_id, incident_id in pairs:
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
                pruned += 1
        self._session.flush()
        return pruned

    def retire_all_stale_incidents(self, now: datetime, stale_after_seconds: int) -> int:
        """Retire stale incidents across every organization; return the count retired."""
        org_ids = self._session.scalars(
            select(IncidentRecord.organization_id).distinct()
        ).all()
        return sum(
            self.retire_stale_incidents(org_id, now, stale_after_seconds) for org_id in org_ids
        )

    def archive_incidents(self, cutoff: datetime, batch: int = 500) -> int:
        """Delete resolved/stale incidents whose last activity predates the archive cutoff."""
        return self._batched_delete(
            IncidentRecord,
            IncidentRecord.id,
            (
                IncidentRecord.status.in_(
                    (IncidentLifecycle.RESOLVED.value, IncidentLifecycle.STALE.value)
                )
            )
            & (IncidentRecord.last_seen.is_not(None))
            & (IncidentRecord.last_seen < cutoff),
            batch,
        )

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
