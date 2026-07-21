# Purpose: operational readiness for asynchronous work — can this deployment actually reconstruct
#   incidents, not merely reach its database?
# Responsibilities: derive queue depth, queue age, stuck claims, failed-job count, last successful
#   job, and reconstruction lag from the durable job table, and classify them against configured
#   thresholds. Deliberately separate from HTTP instance readiness: a stalled worker must not
#   deregister every API replica from the load balancer.
# Dependencies: records, settings. Read-only; aggregate counts only, never per-organization detail.
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config.settings import Settings
from app.models.records import ReconstructionJobRecord


def _age_seconds(moment: datetime | None, now: datetime) -> float | None:
    if moment is None:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return round((now - moment).total_seconds(), 3)


def worker_status(session: Session, settings: Settings) -> dict[str, object]:
    """Aggregate reconstruction-worker health.

    There is no separate heartbeat channel, so liveness is DERIVED from the last completed job. That
    is reported honestly as `heartbeat_source: derived_from_last_completed_job` rather than implying
    a dedicated heartbeat exists.
    """
    now = datetime.now(UTC)

    queue_depth = int(
        session.execute(
            select(func.count())
            .select_from(ReconstructionJobRecord)
            .where(ReconstructionJobRecord.status == "pending")
        ).scalar()
        or 0
    )
    oldest_pending = session.execute(
        select(func.min(ReconstructionJobRecord.created_at)).where(
            ReconstructionJobRecord.status == "pending"
        )
    ).scalar()
    # A claimed job that never completed means a worker died mid-flight.
    stuck_claimed = int(
        session.execute(
            select(func.count())
            .select_from(ReconstructionJobRecord)
            .where(ReconstructionJobRecord.status == "claimed")
        ).scalar()
        or 0
    )
    failed_jobs = int(
        session.execute(
            select(func.count())
            .select_from(ReconstructionJobRecord)
            .where(ReconstructionJobRecord.status == "failed")
        ).scalar()
        or 0
    )
    last_success = session.execute(
        select(func.max(ReconstructionJobRecord.processed_at)).where(
            ReconstructionJobRecord.status == "done"
        )
    ).scalar()

    queue_age = _age_seconds(oldest_pending, now)
    heartbeat_age = _age_seconds(last_success, now)

    # Classification. A deployment that has never had work is healthy, not stalled: absence of jobs
    # is not evidence of a dead worker.
    reasons: list[str] = []
    if queue_age is not None and queue_age > settings.worker_max_queue_age_seconds:
        reasons.append("queue_age_exceeded")
    if stuck_claimed > 0 and (
        queue_age is None or queue_age > settings.worker_max_queue_age_seconds
    ):
        reasons.append("claimed_jobs_not_completing")
    if failed_jobs > settings.worker_max_failed_jobs:
        reasons.append("failed_job_threshold_exceeded")

    healthy = not reasons
    return {
        "status": "ok" if healthy else "stalled",
        "queue_depth": queue_depth,
        "queue_age_seconds": queue_age,
        "reconstruction_lag_seconds": queue_age,
        "stuck_claimed_jobs": stuck_claimed,
        "failed_job_count": failed_jobs,
        "last_successful_job_at": last_success.isoformat() if last_success else None,
        "heartbeat_age_seconds": heartbeat_age,
        "heartbeat_source": "derived_from_last_completed_job",
        "reasons": reasons,
        "thresholds": {
            "max_queue_age_seconds": settings.worker_max_queue_age_seconds,
            "max_failed_jobs": settings.worker_max_failed_jobs,
        },
    }


def workers_healthy(status: dict[str, object]) -> bool:
    return status.get("status") == "ok"
