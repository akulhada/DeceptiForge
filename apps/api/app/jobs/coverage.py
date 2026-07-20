# Purpose: scheduled coverage calculation job.
# Responsibilities: for each organization with any protected surface, compute a deterministic
#   coverage result and persist an immutable snapshot (idempotent by source_state_hash, so a run
#   that observes unchanged state creates nothing new). Organization-scoped, bounded, retryable, and
#   guarded by an advisory lock so concurrent cron invocations produce one snapshot. Gated on the
#   flag. Run as: python -m app.jobs.coverage. Dependencies: engine, repository, settings.
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select

from app.config.settings import Settings, get_settings
from app.jobs._runtime import advisory_lock, job_session, log_event
from app.models.records import (
    AgentSensorRecord,
    BrowserSensorRecord,
    McpConnectorRecord,
    RagConnectorRecord,
    RepositoryRecord,
)
from app.repositories.coverage import CoverageRepository
from app.services.coverage_engine import engine

_LOCK_KEY = 0x44465F434F56  # "DF_COV"


def _organizations(session) -> set[UUID]:  # type: ignore[no-untyped-def]
    orgs: set[UUID] = set()
    for model in (
        RepositoryRecord, RagConnectorRecord, McpConnectorRecord, BrowserSensorRecord,
        AgentSensorRecord,
    ):
        orgs.update(session.scalars(select(model.organization_id).distinct()).all())
    return orgs


def run(settings: Settings | None = None) -> dict[str, int]:
    """Execute one coverage pass across organizations; return counts."""
    settings = settings or get_settings()
    if not settings.coverage_engine_enabled:
        log_event("coverage_job_disabled")
        return {}
    results = {"organizations": 0, "snapshots_created": 0}
    with job_session() as session:
        with advisory_lock(session, _LOCK_KEY) as acquired:
            if not acquired:
                log_event("coverage_job_skipped_locked")
                return {}
            repo = CoverageRepository(session)
            for org in _organizations(session):
                result = engine.calculate(session, org, settings)
                _snapshot, created = repo.persist_snapshot(org, result)
                results["organizations"] += 1
                results["snapshots_created"] += int(created)
    log_event("coverage_job_completed", **results)
    return results


if __name__ == "__main__":
    run()
