# Purpose: process enqueued incident-reconstruction work off the ingestion hot path.
# Responsibilities: claim pending reconstruction jobs (safely under concurrency), reconstruct only
#   the incidents touched by each job's strong correlation keys using an indexed related-alert
#   lookup, upsert those incidents, and mark the job complete. Output is deterministic, so
#   reprocessing a job is idempotent. Dependencies: the artifact repository and the engine.
from __future__ import annotations

from app.repositories.artifacts import ArtifactRepository
from app.services.incident_reconstruction.engine import (
    IncidentConfig,
    IncidentReconstructionEngine,
)

_DEFAULT_BATCH = 100


class ReconstructionWorker:
    """Drains the reconstruction work queue in bounded batches."""

    def __init__(
        self,
        repository: ArtifactRepository,
        engine: IncidentReconstructionEngine | None = None,
        *,
        window_seconds: int = 3600,
        batch: int = _DEFAULT_BATCH,
    ) -> None:
        self._repo = repository
        self._engine = engine or IncidentReconstructionEngine()
        self._config = IncidentConfig(correlation_window_seconds=window_seconds)
        self._batch = batch

    def run_once(self, organization_id: object | None = None) -> int:
        """Claim and process one batch of jobs; return the number processed."""
        from uuid import UUID

        org_filter = organization_id if isinstance(organization_id, UUID) else None
        jobs = self._repo.claim_reconstruction_jobs(self._batch, org_filter)
        for job in jobs:
            try:
                related = self._repo.related_alerts(
                    job.organization_id,
                    trace_identifier=job.trace_identifier,
                    decoy_id=job.decoy_id,
                    affected_placement_id=job.affected_placement_id,
                    correlation_id=job.correlation_id,
                    window_start=job.window_start,
                    window_end=job.window_end,
                )
                if related:
                    incidents = self._engine.reconstruct(
                        related, self._config, organization_id=job.organization_id
                    )
                    self._repo.upsert_incidents_for_organization(job.organization_id, incidents)
                self._repo.complete_reconstruction_job(job.id, ok=True)
            except Exception:  # noqa: BLE001 - a failed job is marked, not left to block the queue
                self._repo.complete_reconstruction_job(job.id, ok=False)
        return len(jobs)

    def drain(self, organization_id: object | None = None) -> int:
        """Process batches until the queue is empty; return the total processed."""
        total = 0
        while True:
            processed = self.run_once(organization_id)
            total += processed
            if processed == 0:
                return total
