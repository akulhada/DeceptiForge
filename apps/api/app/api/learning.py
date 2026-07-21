# Purpose: HTTP surface for controlled learning — analyst feedback plus the model-version lifecycle.
# Responsibilities: organization-scoped, permission-checked capture of bounded analyst feedback, and
#   a review workflow (list/inspect/calibrate/submit/approve/reject/activate/rollback) where no
#   route can activate an unapproved candidate and no feedback mutates active weights. Duties
#   is enforced by scope (admin calibrates/reviews; owner approves/activates) and by actor identity.
# Dependencies: repository, learning services, auth, settings, rate limiter, metrics.
from __future__ import annotations

import re
from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.config.settings import Settings, get_settings
from app.dependencies import get_db
from app.models.domain.learning import (
    FEATURE_SCHEMA_VERSION,
    FeedbackType,
    ModelStatus,
    OutcomeType,
)
from app.repositories.learning import LearningRepository
from app.security import require_scope
from app.services.api_keys import AuthContext
from app.services.learning import versions as lifecycle
from app.services.learning.versions import VersionTransitionError, VersionView
from app.services.metrics import emit
from app.services.rate_limit import get_rate_limiter, rate_limit_key

router = APIRouter(tags=["learning"])

_TARGET_KINDS = {"recommendation", "alert", "incident"}
# Comments are sanitized to plain prose: no path separators, URLs, or secret-like tokens survive.
_COMMENT_STRIP = re.compile(r"(?i)([/\\]|://|-----BEGIN|\b(secret|token|password|api[_-]?key)\b)")


def _require_enabled(settings: Settings) -> None:
    if not settings.learning_enabled:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "learning is not enabled")


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "unknown")


def _sanitize_comment(comment: str | None, settings: Settings) -> str | None:
    """Bound and neutralize a free-text comment. Never used in online scoring."""
    if comment is None:
        return None
    cleaned = _COMMENT_STRIP.sub("[redacted]", comment.strip())
    return cleaned[: settings.learning_max_feedback_comment_length] or None


def _rate_limit(auth: AuthContext, settings: Settings, request_id: str) -> None:
    if not get_rate_limiter().allow(
        rate_limit_key(
            endpoint="learning:feedback", organization_id=auth.organization_id, actor=auth.key_id
        ),
        settings.learning_feedback_rate_limit_per_minute,
    ):
        emit("learning_feedback_rate_limited", organization_id=str(auth.organization_id))
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "feedback rate limit exceeded",
            headers={"Retry-After": "60"},
        )


class AnalystFeedbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    feedback_type: FeedbackType
    corrected_severity: str | None = Field(default=None, max_length=32)
    usefulness: bool | None = None
    reasoning_assessment: str | None = Field(default=None, max_length=32)
    comment: str | None = Field(default=None, max_length=2000)


class FeedbackResponse(BaseModel):
    id: UUID
    revision: int
    feedback_type: str
    recorded: bool
    # Stated explicitly so a caller cannot mistake feedback for a behavior change.
    active_weights_changed: bool = False


class ModelVersionSummary(BaseModel):
    id: UUID
    scope: str
    algorithm_name: str
    algorithm_version: str
    feature_schema_version: str
    status: str
    training_event_count: int
    training_window_start: datetime
    training_window_end: datetime
    created_at: datetime
    activated_at: datetime | None = None


class RollbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1, max_length=256)


def _summary(record) -> ModelVersionSummary:  # type: ignore[no-untyped-def]
    return ModelVersionSummary(
        id=record.id,
        scope=record.scope,
        algorithm_name=record.algorithm_name,
        algorithm_version=record.algorithm_version,
        feature_schema_version=record.feature_schema_version,
        status=record.status,
        training_event_count=record.training_event_count,
        training_window_start=record.training_window_start,
        training_window_end=record.training_window_end,
        created_at=record.created_at,
        activated_at=record.activated_at,
    )


def _view(record) -> VersionView:  # type: ignore[no-untyped-def]
    from app.models.domain.learning import ModelScope

    return VersionView(
        id=record.id,
        organization_id=record.organization_id,
        scope=ModelScope(record.scope),
        status=ModelStatus(record.status),
        feature_schema_version=record.feature_schema_version,
        requested_by_actor_id=record.requested_by_actor_id,
        safety_constraints_preserved=record.safety_constraints_preserved,
    )


def _load(repository: LearningRepository, version_id: UUID):  # type: ignore[no-untyped-def]
    record = repository.get_version(version_id)
    if record is None:
        # 404 rather than 403 so a probe cannot confirm another tenant's version id exists.
        raise HTTPException(status.HTTP_404_NOT_FOUND, "model version not found")
    return record


# ---- analyst feedback ----------------------------------------------------------------------------


def _feedback(
    target_kind: str,
    target_id: UUID,
    body: AnalystFeedbackRequest,
    request: Request,
    session: Session,
    auth: AuthContext,
) -> FeedbackResponse:
    settings = get_settings()
    _require_enabled(settings)
    _rate_limit(auth, settings, _request_id(request))
    repository = LearningRepository(session, auth.organization_id)
    record = repository.record_feedback(
        actor_id=auth.key_id,
        target_kind=target_kind,
        target_id=target_id,
        feedback_type=body.feedback_type,
        original_value=None,
        corrected_value=body.corrected_severity or body.reasoning_assessment,
        normalized_comment=_sanitize_comment(body.comment, settings),
    )
    emit(
        "learning_feedback_submitted",
        organization_id=str(auth.organization_id),
        request_id=_request_id(request),
        feedback_type=body.feedback_type.value,
        target_kind=target_kind,
    )
    # Feedback is evidence for a future offline calibration run only.
    return FeedbackResponse(
        id=record.id,
        revision=record.revision,
        feedback_type=record.feedback_type,
        recorded=True,
        active_weights_changed=False,
    )


@router.post(
    "/placement-recommendations/{recommendation_id}/feedback", response_model=FeedbackResponse
)
def recommendation_feedback(
    recommendation_id: UUID,
    body: AnalystFeedbackRequest,
    request: Request,
    session: Session = Depends(get_db),
    auth: AuthContext = Depends(require_scope("learning:feedback")),
) -> FeedbackResponse:
    return _feedback("recommendation", recommendation_id, body, request, session, auth)


@router.post("/alerts/{alert_id}/feedback", response_model=FeedbackResponse)
def alert_feedback(
    alert_id: UUID,
    body: AnalystFeedbackRequest,
    request: Request,
    session: Session = Depends(get_db),
    auth: AuthContext = Depends(require_scope("learning:feedback")),
) -> FeedbackResponse:
    return _feedback("alert", alert_id, body, request, session, auth)


@router.post("/incidents/{incident_id}/feedback", response_model=FeedbackResponse)
def incident_feedback(
    incident_id: UUID,
    body: AnalystFeedbackRequest,
    request: Request,
    session: Session = Depends(get_db),
    auth: AuthContext = Depends(require_scope("learning:feedback")),
) -> FeedbackResponse:
    return _feedback("incident", incident_id, body, request, session, auth)


# ---- model version administration ----------------------------------------------------------------


@router.get("/learning/model-versions", response_model=list[ModelVersionSummary])
def list_versions(
    session: Session = Depends(get_db),
    auth: AuthContext = Depends(require_scope("learning:read")),
) -> list[ModelVersionSummary]:
    _require_enabled(get_settings())
    repository = LearningRepository(session, auth.organization_id)
    return [_summary(r) for r in repository.list_versions()]


@router.get("/learning/model-versions/{version_id}", response_model=ModelVersionSummary)
def get_version(
    version_id: UUID,
    session: Session = Depends(get_db),
    auth: AuthContext = Depends(require_scope("learning:read")),
) -> ModelVersionSummary:
    _require_enabled(get_settings())
    repository = LearningRepository(session, auth.organization_id)
    return _summary(_load(repository, version_id))


@router.get("/learning/model-versions/{version_id}/changes")
def version_changes(
    version_id: UUID,
    session: Session = Depends(get_db),
    auth: AuthContext = Depends(require_scope("learning:read")),
) -> dict[str, object]:
    """The explainable calibration report: window, counts, exclusions, weights, and limitations."""
    import json

    _require_enabled(get_settings())
    repository = LearningRepository(session, auth.organization_id)
    record = _load(repository, version_id)
    return {"version_id": str(record.id), "report": json.loads(record.report or "{}")}


@router.post("/learning/calibration-runs", response_model=list[ModelVersionSummary])
def run_calibration(
    request: Request,
    session: Session = Depends(get_db),
    auth: AuthContext = Depends(require_scope("learning:calibrate")),
) -> list[ModelVersionSummary]:
    """Generate a candidate from this organization's own events. Never activates anything."""
    from datetime import timedelta

    from app.jobs.learning_calibration import ALGORITHM_NAME, ALGORITHM_VERSION
    from app.services.learning.calibration import build_candidate

    settings = get_settings()
    _require_enabled(settings)
    repository = LearningRepository(session, auth.organization_id)
    window_end = datetime.now(UTC)
    window_start = window_end - timedelta(days=settings.learning_event_retention_days)
    report = build_candidate(
        repository.observations(window_start=window_start, window_end=window_end),
        window_start=window_start,
        window_end=window_end,
        previous=None,
        min_samples=settings.learning_min_events_for_calibration,
        min_distinct_actors=settings.learning_min_distinct_actors,
        max_actor_contribution=settings.learning_max_actor_contribution,
        min_observation_hours=settings.learning_min_observation_hours,
        min_healthy_monitoring_ratio=settings.learning_min_healthy_monitoring_ratio,
    )
    emit(
        "learning_calibration_requested",
        organization_id=str(auth.organization_id),
        request_id=_request_id(request),
        produced=bool(report),
    )
    if report is None:
        return []
    candidate = repository.create_candidate(
        report,
        algorithm_name=ALGORITHM_NAME,
        algorithm_version=ALGORITHM_VERSION,
        requested_by_actor_id=auth.key_id,
    )
    return [_summary(candidate)]


def _transition(
    version_id: UUID,
    target: ModelStatus,
    session: Session,
    auth: AuthContext,
    request: Request,
    *,
    reason: str | None = None,
) -> ModelVersionSummary:
    settings = get_settings()
    _require_enabled(settings)
    repository = LearningRepository(session, auth.organization_id)
    record = _load(repository, version_id)
    view = _view(record)
    try:
        if target is ModelStatus.APPROVED:
            lifecycle.approve(
                view, organization_id=auth.organization_id, approver_actor_id=auth.key_id
            )
            repository.set_status(record, target, approver_actor_id=auth.key_id)
        elif target is ModelStatus.ACTIVE:
            lifecycle.activate(
                view,
                organization_id=auth.organization_id,
                require_approval=settings.learning_require_approval,
            )
            repository.set_status(record, target)
        elif target is ModelStatus.ROLLED_BACK:
            lifecycle.rollback(view, organization_id=auth.organization_id, reason=reason or "")
            repository.set_status(record, target, rollback_reason=reason)
        else:
            lifecycle.ensure_same_organization(view, auth.organization_id)
            lifecycle.ensure_transition(view.status, target)
            repository.set_status(record, target)
    except VersionTransitionError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
    emit(
        "learning_version_transition",
        organization_id=str(auth.organization_id),
        request_id=_request_id(request),
        version_id=str(version_id),
        target=target.value,
    )
    return _summary(record)


@router.post(
    "/learning/model-versions/{version_id}/submit-review", response_model=ModelVersionSummary
)
def submit_review(
    version_id: UUID,
    request: Request,
    session: Session = Depends(get_db),
    auth: AuthContext = Depends(require_scope("learning:review")),
) -> ModelVersionSummary:
    return _transition(version_id, ModelStatus.UNDER_REVIEW, session, auth, request)


@router.post("/learning/model-versions/{version_id}/approve", response_model=ModelVersionSummary)
def approve_version(
    version_id: UUID,
    request: Request,
    session: Session = Depends(get_db),
    auth: AuthContext = Depends(require_scope("learning:approve")),
) -> ModelVersionSummary:
    return _transition(version_id, ModelStatus.APPROVED, session, auth, request)


@router.post("/learning/model-versions/{version_id}/reject", response_model=ModelVersionSummary)
def reject_version(
    version_id: UUID,
    request: Request,
    session: Session = Depends(get_db),
    auth: AuthContext = Depends(require_scope("learning:review")),
) -> ModelVersionSummary:
    return _transition(version_id, ModelStatus.REJECTED, session, auth, request)


@router.post("/learning/model-versions/{version_id}/activate", response_model=ModelVersionSummary)
def activate_version(
    version_id: UUID,
    request: Request,
    session: Session = Depends(get_db),
    auth: AuthContext = Depends(require_scope("learning:activate")),
) -> ModelVersionSummary:
    return _transition(version_id, ModelStatus.ACTIVE, session, auth, request)


@router.post("/learning/model-versions/{version_id}/rollback", response_model=ModelVersionSummary)
def rollback_version(
    version_id: UUID,
    body: RollbackRequest,
    request: Request,
    session: Session = Depends(get_db),
    auth: AuthContext = Depends(require_scope("learning:rollback")),
) -> ModelVersionSummary:
    return _transition(
        version_id, ModelStatus.ROLLED_BACK, session, auth, request, reason=body.reason
    )


@router.get("/learning/metrics")
def learning_metrics(
    session: Session = Depends(get_db),
    auth: AuthContext = Depends(require_scope("learning:read")),
) -> dict[str, object]:
    """Aggregate-only view. Never exposes raw events, comments, or another tenant's data."""
    import json

    _require_enabled(get_settings())
    repository = LearningRepository(session, auth.organization_id)
    active = repository.active_version()
    versions = repository.list_versions()
    return {
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "active_version_id": str(active.id) if active else None,
        "active_algorithm_version": active.algorithm_version if active else None,
        "active_version_age_days": (
            (datetime.now(UTC) - active.activated_at).days
            if active and active.activated_at
            else None
        ),
        "candidate_count": sum(1 for v in versions if v.status == ModelStatus.CANDIDATE.value),
        "learning_event_count": repository.event_count(),
        "metrics": json.loads(active.metrics) if active else {},
        "supported_outcome_types": [o.value for o in OutcomeType],
    }
