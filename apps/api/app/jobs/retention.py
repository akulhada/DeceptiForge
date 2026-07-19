# Purpose: scheduled data-retention job.
# Responsibilities: delete aged monitoring events, aged alerts, processed reconstruction jobs, and
#   revoked/expired API keys, and prune narrative revisions to the configured count. Bounded and
#   batched, idempotent, organization-safe, and guarded by an advisory lock so concurrent cron
#   invocations do not collide. Run as `python -m app.jobs.retention`. Dependencies: repository.
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.config.settings import Settings, get_settings
from app.jobs._runtime import advisory_lock, job_session, log_event
from app.repositories.artifacts import ArtifactRepository

_LOCK_KEY = 0x44465F52544E  # "DF_RTN"


def run(settings: Settings | None = None) -> dict[str, int]:
    """Execute one retention pass; return the counts removed/pruned per category."""
    settings = settings or get_settings()
    now = datetime.now(UTC)
    batch = settings.retention_batch_size
    results: dict[str, int] = {}
    with job_session() as session:
        with advisory_lock(session, _LOCK_KEY) as acquired:
            if not acquired:
                log_event("retention_skipped_locked")
                return {}
            repo = ArtifactRepository(session)
            results["monitoring_events"] = repo.purge_detection_events(
                now - timedelta(days=settings.monitoring_event_retention_days), batch
            )
            results["alerts"] = repo.purge_alerts(
                now - timedelta(days=settings.alert_retention_days), batch
            )
            results["reconstruction_jobs"] = repo.purge_reconstruction_jobs(
                now - timedelta(days=settings.reconstruction_job_retention_days), batch
            )
            results["api_keys"] = repo.purge_expired_api_keys(
                now, now - timedelta(days=settings.api_key_retention_days), batch
            )
            results["narrative_revisions"] = repo.prune_all_narrative_revisions(
                settings.narrative_revision_retention_count
            )
    log_event("retention_completed", **results)
    return results


if __name__ == "__main__":
    run()
