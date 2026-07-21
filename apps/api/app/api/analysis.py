# Purpose: HTTP surface for the Interactive Demo Lab — deterministic, stateless preview analysis.
# Responsibilities: authenticate + org-scope + permission-check (analysis:preview), validate the
#   shared signals contract, enforce collection bounds and a dedicated rate limit, run ONLY the
#   deterministic engines, and return an explainable result with a request id. Never persists user
#   input/results, never opens a path, never calls GPT, never mutates deployment/alert/incident
#   state. Body-size 413 is enforced globally by BodyLimitMiddleware.
# Dependencies: preview service, scenarios, auth, rate limiter, settings, metrics.
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.config.settings import get_settings
from app.dependencies import get_db
from app.models.domain.analysis_preview import AnalysisPreviewResponse
from app.models.domain.analysis_signals import (
    MAX_TOTAL_PATHS,
    RepositorySignals,
    total_representative_paths,
)
from app.security import require_scope
from app.services.analysis_lab import AnalysisPreviewService
from app.services.analysis_lab.scenarios import load_scenarios
from app.services.api_keys import AuthContext
from app.services.learning.applied import ActiveCalibration
from app.services.metrics import emit
from app.services.rate_limit import get_rate_limiter, rate_limit_key

router = APIRouter(prefix="/api/v1/analysis", tags=["analysis"])

_service = AnalysisPreviewService()


class AnalysisOptions(BaseModel):
    """Strict allowlist — no arbitrary engine names, classes, or executable configuration."""

    model_config = ConfigDict(extra="forbid")

    include_alternatives: bool = True
    maximum_recommendations: int = Field(default=10, ge=1, le=20)
    minimum_confidence: float = Field(default=0.0, ge=0, le=1)


class AnalysisPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    signals: RepositorySignals
    scenario_id: str | None = Field(default=None, max_length=64)
    options: AnalysisOptions | None = None


class ScenarioSummary(BaseModel):
    id: str
    name: str
    description: str
    signals: dict[str, object]


def _active_calibration(session: Session, auth: AuthContext) -> ActiveCalibration:
    """Read this organization's approved, active calibration. Read-only; never cross-tenant."""
    settings = get_settings()
    if not settings.learning_enabled:
        return ActiveCalibration()
    from app.models.domain.learning import CalibrationMetrics, CalibrationWeights
    from app.repositories.learning import LearningRepository

    record = LearningRepository(session, auth.organization_id).active_version()
    if record is None:
        return ActiveCalibration()
    metrics = CalibrationMetrics.model_validate_json(record.metrics or "{}")
    samples = {m.cohort: m.sample_count for m in metrics.acceptance if m.sufficient}
    intervals = {
        m.cohort: (m.wilson_low, m.wilson_high) for m in metrics.acceptance if m.sufficient
    }
    return ActiveCalibration(
        model_version_id=record.id,
        weights=CalibrationWeights.model_validate_json(record.weights or "{}"),
        organization_specific=record.organization_id is not None,
        global_aggregate_used=False,
        cohort_samples=samples,
        cohort_intervals=intervals,
    )


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "unknown")


@router.get("/scenarios", response_model=list[ScenarioSummary])
def list_scenarios(
    auth: AuthContext = Depends(require_scope("analysis:preview")),
) -> list[ScenarioSummary]:
    """Prepared, fictional scenarios for the lab. Requires org-scoped analysis:preview auth."""
    return [
        ScenarioSummary(id=s.scenario_id, name=s.name, description=s.description, signals=s.signals)
        for s in load_scenarios()
    ]


@router.post("/preview", response_model=AnalysisPreviewResponse)
def preview_analysis(
    payload: AnalysisPreviewRequest,
    request: Request,
    session: Session = Depends(get_db),
    auth: AuthContext = Depends(require_scope("analysis:preview")),
) -> AnalysisPreviewResponse:
    settings = get_settings()
    request_id = _request_id(request)
    org = str(auth.organization_id)

    # Dedicated per-organization+actor budget (never the monitoring-ingest limit).
    if not get_rate_limiter().allow(
        rate_limit_key(
            endpoint="analysis:preview", organization_id=auth.organization_id, actor=auth.key_id
        ),
        settings.analysis_preview_rate_limit_per_minute,
    ):
        emit("analysis_rate_limited", organization_id=org, request_id=request_id)
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "analysis rate limit exceeded",
            headers={"Retry-After": "60"},
        )

    signals = payload.signals
    # Aggregate-path bound is enforced before analysis (collection bounds handled by the contract).
    if total_representative_paths(signals) > MAX_TOTAL_PATHS:
        emit(
            "analysis_rejected", organization_id=org, request_id=request_id, reason="too_many_paths"
        )
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"too many representative paths (limit {MAX_TOTAL_PATHS})",
        )

    ignored_fields = tuple(sorted((signals.model_extra or {}).keys()))
    options = payload.options or AnalysisOptions()
    emit(
        "analysis_requested",
        organization_id=org,
        request_id=request_id,
        scenario_id=payload.scenario_id or "custom",
        payload_paths=total_representative_paths(signals),
    )
    result = _service.analyze(
        signals,
        organization_id=org,
        request_id=request_id,
        scenario_id=payload.scenario_id,
        ignored_fields=ignored_fields,
        max_recommendations=options.maximum_recommendations,
        minimum_confidence=options.minimum_confidence,
        calibration=_active_calibration(session, auth),
    )
    emit(
        "analysis_succeeded",
        organization_id=org,
        request_id=request_id,
        scenario_id=payload.scenario_id or "custom",
        overall_confidence=result.confidence.overall,
        warning_count=len(result.warnings),
    )
    return result
