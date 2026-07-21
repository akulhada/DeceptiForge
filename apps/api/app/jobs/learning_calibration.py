# Purpose: scheduled offline calibration job.
# Responsibilities: per organization, load a bounded window of that organization's outcomes, apply
#   attribution rules, enforce minimum sample sizes, and persist a CANDIDATE model version with an
#   explainable report. Never activates anything, never joins across tenants, never reads raw
#   content. Advisory-locked, retry-safe, idempotent for an unchanged event set, and skipped on a
#   non-leader region. Gated on LEARNING_ENABLED. Run as: python -m app.jobs.learning_calibration.
# Dependencies: repository, calibration service, settings, reliability fencing.
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select

from app.config.settings import Settings, get_settings
from app.jobs._runtime import advisory_lock, job_session, log_event
from app.models.domain.learning import ModelStatus
from app.models.records import LearningModelVersionRecord, PlacementOutcomeRecord
from app.repositories.learning import LearningRepository
from app.services.learning.calibration import build_candidate
from app.services.reliability.fencing import scheduler_allowed

_LOCK_KEY = 0x44465F4C524E  # "DF_LRN"
ALGORITHM_NAME = "placement-prior-calibration"
ALGORITHM_VERSION = "1.0"


def _organizations(session) -> set[UUID]:  # type: ignore[no-untyped-def]
    return set(session.scalars(select(PlacementOutcomeRecord.organization_id).distinct()).all())


def _previous_weights(session, organization_id: UUID):  # type: ignore[no-untyped-def]
    """The currently active weights for this organization, if any, as the calibration baseline."""
    from app.models.domain.learning import CalibrationWeights

    record = session.scalars(
        select(LearningModelVersionRecord).where(
            LearningModelVersionRecord.organization_id == organization_id,
            LearningModelVersionRecord.status == ModelStatus.ACTIVE.value,
        )
    ).first()
    if record is None:
        return None
    return CalibrationWeights.model_validate_json(record.weights)


def run(settings: Settings | None = None) -> dict[str, int]:
    """Execute one calibration pass. Returns counts; creates candidates only."""
    settings = settings or get_settings()
    result = {"organizations": 0, "candidates": 0, "skipped_insufficient": 0}
    if not settings.learning_enabled:
        log_event("learning_calibration_skipped", reason="disabled")
        return result
    if not scheduler_allowed(settings):
        log_event("learning_calibration_skipped", reason="not_leader_region")
        return result

    window_end = datetime.now(UTC)
    window_start = window_end - timedelta(days=settings.learning_event_retention_days)

    with job_session() as session:
        with advisory_lock(session, _LOCK_KEY) as acquired:
            if not acquired:
                log_event("learning_calibration_skipped", reason="lock_unavailable")
                return result
            for organization_id in sorted(_organizations(session), key=str):
                result["organizations"] += 1
                repository = LearningRepository(session, organization_id)
                observations = repository.observations(
                    window_start=window_start, window_end=window_end
                )
                report = build_candidate(
                    observations,
                    window_start=window_start,
                    window_end=window_end,
                    previous=_previous_weights(session, organization_id),
                    min_samples=settings.learning_min_events_for_calibration,
                    min_distinct_actors=settings.learning_min_distinct_actors,
                    max_actor_contribution=settings.learning_max_actor_contribution,
                    min_observation_hours=settings.learning_min_observation_hours,
                    min_healthy_monitoring_ratio=settings.learning_min_healthy_monitoring_ratio,
                )
                if report is None:
                    result["skipped_insufficient"] += 1
                    log_event(
                        "learning_calibration_insufficient",
                        organization_id=str(organization_id),
                        observed=len(observations),
                    )
                    continue
                candidate = repository.create_candidate(
                    report,
                    algorithm_name=ALGORITHM_NAME,
                    algorithm_version=ALGORITHM_VERSION,
                    requested_by_actor_id=None,  # produced by the service worker, not a human
                )
                result["candidates"] += 1
                log_event(
                    "learning_candidate_created",
                    organization_id=str(organization_id),
                    version_id=str(candidate.id),
                    included=report.included_event_count,
                    excluded=report.excluded_event_count,
                )
    log_event("learning_calibration_completed", **{k: str(v) for k, v in result.items()})
    return result


if __name__ == "__main__":  # pragma: no cover
    run()
