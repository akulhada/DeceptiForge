# Purpose: drive ONE controlled interaction through the real detection pipeline for a judge sandbox,
#   and summarize a sandbox's own state for export.
# Responsibilities: pick an accepted decoy belonging to the sandbox, ingest a touch through the
#   ordinary monitoring path so the alert and incident are produced by the product rather than
#   inserted, and count what exists. Never writes an alert or incident directly.
# Dependencies: artifact repository, pipeline service, reconstruction worker. No HTTP.
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.records import (
    AlertRecord,
    DecoyPlanRecord,
    DetectionEventRecord,
    IncidentRecord,
    RepositoryRecord,
)
from app.services.judge_sandbox import SandboxNamespace, _first_accepted_trace


@dataclass(frozen=True)
class InteractionOutcome:
    trace_identifier: str
    event_recorded: bool
    alert_id: UUID | None
    incident_id: UUID | None


class JudgeInteractionService:
    """One controlled interaction, and read-only summaries, for a single sandbox."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def interact(self, namespace: SandboxNamespace) -> InteractionOutcome | None:
        """Touch an accepted decoy in this sandbox. Returns None when there is nothing to touch.

        The decoy plan is looked up by the sandbox's own organization, so the interaction cannot
        reach another organization's asset even if one were somehow named. Reconstruction is drained
        inline so the judge sees the resulting incident in the same session; in production this is
        an asynchronous worker, and the code path it runs is identical.
        """
        from app.repositories.artifacts import ArtifactRepository
        from app.services.incident_reconstruction import ReconstructionWorker
        from app.services.pipeline import PipelineService

        repository = ArtifactRepository(self._session)
        organization_id = namespace.organization_id

        latest = self._latest_repository_id(organization_id)
        if latest is None:
            return None
        decoy = repository.latest_decoy_plan(organization_id, latest)
        if decoy is None:
            return None
        decoy_plan_id, decoy_plan = decoy
        reports = repository.reports_for_decoy_plan(organization_id, decoy_plan_id)
        trace = _first_accepted_trace(decoy_plan, reports)
        if trace is None:
            # Only accepted decoys are monitored. Refusing here is honest: a judge should not be
            # shown an alert for an asset the product would never have deployed.
            return None

        pipeline = PipelineService(repository, organization_id)
        event, alert = pipeline.ingest_event(
            decoy_plan_id,
            "repository",
            "src/exfiltrated.py",
            f"copied {trace} to laptop",
        )
        ReconstructionWorker(repository).drain(organization_id)

        return InteractionOutcome(
            trace_identifier=trace,
            event_recorded=event is not None,
            alert_id=self._latest_alert_id(organization_id) if alert is not None else None,
            incident_id=self._latest_incident_id(organization_id),
        )

    def summarize(self, namespace: SandboxNamespace) -> dict[str, int]:
        """Aggregate counts for this sandbox only. Carries no content, traces or payloads."""
        organization_id = namespace.organization_id
        decoy_assets = 0
        plan_rows = (
            self._session.execute(
                select(DecoyPlanRecord).where(DecoyPlanRecord.organization_id == organization_id)
            )
            .scalars()
            .all()
        )
        for row in plan_rows:
            decoy_assets += _asset_count(row)

        return {
            "repositories": self._count(RepositoryRecord, organization_id),
            "decoy_assets": decoy_assets,
            "monitoring_events": self._count(DetectionEventRecord, organization_id),
            "alerts": self._count(AlertRecord, organization_id),
            "incidents": self._count(IncidentRecord, organization_id),
        }

    # ---- internals -------------------------------------------------------------------------

    def _count(self, model: type, organization_id: UUID) -> int:
        return int(
            self._session.execute(
                select(func.count())
                .select_from(model)
                .where(model.organization_id == organization_id)  # type: ignore[attr-defined]
            ).scalar()
            or 0
        )

    def _latest_repository_id(self, organization_id: UUID) -> UUID | None:
        return self._session.execute(
            select(RepositoryRecord.id)
            .where(RepositoryRecord.organization_id == organization_id)
            .order_by(RepositoryRecord.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()

    def _latest_alert_id(self, organization_id: UUID) -> UUID | None:
        return self._session.execute(
            select(AlertRecord.id)
            .where(AlertRecord.organization_id == organization_id)
            .order_by(AlertRecord.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()

    def _latest_incident_id(self, organization_id: UUID) -> UUID | None:
        return self._session.execute(
            select(IncidentRecord.id)
            .where(IncidentRecord.organization_id == organization_id)
            .order_by(IncidentRecord.created_at.desc())
            .limit(1)
        ).scalar_one_or_none()


def _asset_count(row: DecoyPlanRecord) -> int:
    """Count assets without trusting the stored JSON shape."""
    import json

    try:
        payload = json.loads(row.data or "{}")
    except ValueError:
        return 0
    assets = payload.get("assets")
    return len(assets) if isinstance(assets, list) else 0
