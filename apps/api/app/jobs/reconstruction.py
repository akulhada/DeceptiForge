# Purpose: worker entrypoint that drains the incident-reconstruction queue.
# Responsibilities: process enqueued reconstruction work off the ingestion hot path, safely under
#   concurrent invocation (per-row claim), and report how much was processed. Run as a separate
#   worker/cron command: `python -m app.jobs.reconstruction`. Dependencies: repository, worker.
from __future__ import annotations

from app.jobs._runtime import job_session, log_event
from app.repositories.artifacts import ArtifactRepository
from app.services.incident_reconstruction import ReconstructionWorker


def run() -> int:
    """Drain all pending reconstruction jobs; return the number processed."""
    with job_session() as session:
        processed = ReconstructionWorker(ArtifactRepository(session)).drain()
    log_event("reconstruction_drained", processed=processed)
    return processed


if __name__ == "__main__":
    run()
