# Purpose: scheduled incident-lifecycle job.
# Responsibilities: retire stale incidents (no activity within the configured window) across every
#   organization and archive long-resolved/stale incidents past the archive window. Idempotent,
#   organization-safe, and advisory-locked against concurrent runs. Run as
#   `python -m app.jobs.incident_lifecycle`. Dependencies: repository, settings.
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.config.settings import Settings, get_settings
from app.jobs._runtime import advisory_lock, job_session, log_event
from app.repositories.artifacts import ArtifactRepository

_LOCK_KEY = 0x44465F494C43  # "DF_ILC"


def run(settings: Settings | None = None) -> dict[str, int]:
    """Execute one incident-lifecycle pass; return counts retired and archived."""
    settings = settings or get_settings()
    now = datetime.now(UTC)
    results: dict[str, int] = {}
    with job_session() as session:
        with advisory_lock(session, _LOCK_KEY) as acquired:
            if not acquired:
                log_event("incident_lifecycle_skipped_locked")
                return {}
            repo = ArtifactRepository(session)
            results["retired"] = repo.retire_all_stale_incidents(
                now, settings.incident_stale_after_seconds
            )
            results["archived"] = repo.archive_incidents(
                now - timedelta(seconds=settings.incident_archive_after_seconds),
                settings.retention_batch_size,
            )
    log_event("incident_lifecycle_completed", **results)
    return results


if __name__ == "__main__":
    run()
