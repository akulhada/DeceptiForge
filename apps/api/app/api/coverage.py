# Purpose: HTTP surface for the measured coverage engine — snapshots, surfaces, gaps, ranked
#   recommendations, methodology, policy, and manual recalculation.
# Responsibilities: read immutable snapshots and pre-aggregated surfaces without recomputing,
#   trigger an idempotent recalculation, manage the versioned policy, and accept/dismiss a
#   recommendation (advisory only — never an automatic deployment). Org + permission scoped.
# Dependencies: engine, repository, formula (methodology), settings, auth.
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config.settings import Settings, get_settings
from app.dependencies import get_db
from app.models.domain.coverage import METHODOLOGY_VERSION, CoveragePolicyDoc
from app.repositories.coverage import CoverageRepository
from app.security import require_scope
from app.services.api_keys import AuthContext
from app.services.coverage_engine import engine
from app.services.coverage_engine.formula import DIMENSION_WEIGHTS
from app.services.metrics import emit

router = APIRouter(tags=["coverage"])


class SnapshotSummary(BaseModel):
    id: UUID
    calculated_at: datetime
    overall_score: float
    confidence: float
    covered_weight: float
    total_weight: float
    unknown_weight: float
    active_decoys: int
    active_sensors: int
    unhealthy_sensors: int
    expired_decoys: int
    blind_spot_count: int
    methodology_version: str
    source_state_hash: str


class PolicyBody(BaseModel):
    minimum_acceptable_score: float = Field(default=0.6, ge=0, le=1)
    minimum_sensor_health: float = Field(default=0.5, ge=0, le=1)
    verification_freshness_hours: int = Field(default=168, ge=1)
    maximum_unknown_weight: float = Field(default=0.4, ge=0, le=1)
    recommendation_risk_tolerance: float = Field(default=0.6, ge=0, le=1)


def _require_enabled(settings: Settings) -> None:
    if not settings.coverage_engine_enabled:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "coverage engine is not enabled")


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "unknown")


def _summary(s) -> SnapshotSummary:  # type: ignore[no-untyped-def]
    return SnapshotSummary(
        id=s.id, calculated_at=s.calculated_at, overall_score=s.overall_score,
        confidence=s.confidence, covered_weight=s.covered_weight, total_weight=s.total_weight,
        unknown_weight=s.unknown_weight, active_decoys=s.active_decoys,
        active_sensors=s.active_sensors, unhealthy_sensors=s.unhealthy_sensors,
        expired_decoys=s.expired_decoys, blind_spot_count=s.blind_spot_count,
        methodology_version=s.methodology_version, source_state_hash=s.source_state_hash,
    )


@router.get("/coverage")
def get_coverage(
    auth: AuthContext = Depends(require_scope("coverage:read")),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    settings = get_settings()
    _require_enabled(settings)
    repo = CoverageRepository(session)
    latest = repo.latest_snapshot(auth.organization_id)
    if latest is None:
        # Honest empty state — never fabricate a score.
        return {"status": "no_snapshot", "methodology_version": METHODOLOGY_VERSION}
    return {"status": "ok", "snapshot": _summary(latest).model_dump(mode="json")}


@router.get("/coverage/snapshots", response_model=list[SnapshotSummary])
def list_snapshots(
    auth: AuthContext = Depends(require_scope("coverage:read")),
    session: Session = Depends(get_db),
) -> list[SnapshotSummary]:
    settings = get_settings()
    _require_enabled(settings)
    return [_summary(s) for s in CoverageRepository(session).list_snapshots(auth.organization_id)]


@router.get("/coverage/snapshots/{snapshot_id}")
def get_snapshot(
    snapshot_id: UUID, auth: AuthContext = Depends(require_scope("coverage:read")),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    settings = get_settings()
    _require_enabled(settings)
    import json

    record = CoverageRepository(session).get_snapshot(auth.organization_id, snapshot_id)
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "snapshot not found")
    return {
        "snapshot": _summary(record).model_dump(mode="json"),
        "surfaces": json.loads(record.surfaces_data or "[]"),
    }


@router.get("/coverage/surfaces")
def list_surfaces(
    auth: AuthContext = Depends(require_scope("coverage:read")),
    session: Session = Depends(get_db),
) -> list[dict[str, object]]:
    settings = get_settings()
    _require_enabled(settings)
    return [
        {
            "surface_type": s.surface_type, "external_or_resource_id": s.external_or_resource_id,
            "display_name": s.display_name, "criticality": s.criticality,
            "risk_weight": s.risk_weight, "surface_coverage": s.surface_coverage,
            "confidence": s.confidence, "status": s.status,
        }
        for s in CoverageRepository(session).surfaces(auth.organization_id)
    ]


@router.get("/coverage/gaps")
def list_gaps(
    auth: AuthContext = Depends(require_scope("coverage:read")),
    session: Session = Depends(get_db),
) -> list[dict[str, object]]:
    settings = get_settings()
    _require_enabled(settings)
    repo = CoverageRepository(session)
    latest = repo.latest_snapshot(auth.organization_id)
    if latest is None:
        return []
    return [
        {
            "surface_type": g.surface_type, "external_or_resource_id": g.external_or_resource_id,
            "gap_type": g.gap_type, "severity": g.severity, "reason": g.reason,
            "missing_controls": g.missing_controls,
            "expected_coverage_gain": g.expected_coverage_gain,
        }
        for g in repo.gaps(auth.organization_id, latest.id)
    ]


@router.get("/coverage/recommendations")
def list_recommendations(
    auth: AuthContext = Depends(require_scope("coverage:read")),
    session: Session = Depends(get_db),
) -> list[dict[str, object]]:
    settings = get_settings()
    _require_enabled(settings)
    repo = CoverageRepository(session)
    latest = repo.latest_snapshot(auth.organization_id)
    if latest is None:
        return []
    return [
        {
            "id": str(r.id), "surface_type": r.surface_type,
            "external_or_resource_id": r.external_or_resource_id,
            "recommended_action": r.recommended_action,
            "recommended_decoy_type": r.recommended_decoy_type,
            "target_location": r.target_location,
            "expected_coverage_gain": r.expected_coverage_gain,
            "expected_detection_gain": r.expected_detection_gain,
            "deployment_risk": r.deployment_risk, "false_positive_risk": r.false_positive_risk,
            "implementation_effort": r.implementation_effort, "priority_score": r.priority_score,
            "confidence": r.confidence, "explanation": r.explanation, "status": r.status,
        }
        for r in repo.recommendations(auth.organization_id, latest.id)
    ]


@router.post("/coverage/recommendations/{recommendation_id}/accept")
def accept_recommendation(
    recommendation_id: UUID, request: Request,
    auth: AuthContext = Depends(require_scope("coverage:manage_policy")),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    # Accepting a recommendation records intent only. It never deploys automatically — the operator
    # still creates + approves a deployment through the normal (separation-of-duties) flow.
    settings = get_settings()
    _require_enabled(settings)
    repo = CoverageRepository(session)
    record = repo.get_recommendation(auth.organization_id, recommendation_id)
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "recommendation not found")
    record.status = "accepted"
    session.flush()
    repo.add_audit(
        organization_id=auth.organization_id, actor_id=auth.key_id,
        event_type="recommendation_accepted", request_id=_request_id(request),
        safe_metadata=record.recommended_action,
    )
    return {"status": "accepted", "auto_deployed": False}


@router.post("/coverage/recommendations/{recommendation_id}/dismiss")
def dismiss_recommendation(
    recommendation_id: UUID, request: Request,
    auth: AuthContext = Depends(require_scope("coverage:manage_policy")),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    settings = get_settings()
    _require_enabled(settings)
    repo = CoverageRepository(session)
    record = repo.get_recommendation(auth.organization_id, recommendation_id)
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "recommendation not found")
    record.status = "dismissed"
    session.flush()
    repo.add_audit(
        organization_id=auth.organization_id, actor_id=auth.key_id,
        event_type="recommendation_dismissed", request_id=_request_id(request),
    )
    return {"status": "dismissed"}


@router.post("/coverage/recalculate", response_model=SnapshotSummary)
def recalculate(
    request: Request, auth: AuthContext = Depends(require_scope("coverage:recalculate")),
    session: Session = Depends(get_db),
) -> SnapshotSummary:
    settings = get_settings()
    _require_enabled(settings)
    repo = CoverageRepository(session)
    result = engine.calculate(session, auth.organization_id, settings)
    snapshot, created = repo.persist_snapshot(auth.organization_id, result)
    repo.add_audit(
        organization_id=auth.organization_id, actor_id=auth.key_id, snapshot_id=snapshot.id,
        event_type="coverage_recalculated", request_id=_request_id(request),
        safe_metadata=f"created={created}",
    )
    emit(
        "coverage_recalculated", organization_id=str(auth.organization_id),
        overall=result.overall_score, created=created,
    )
    return _summary(snapshot)


@router.get("/coverage/methodology")
def get_methodology(
    auth: AuthContext = Depends(require_scope("coverage:read")),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    settings = get_settings()
    _require_enabled(settings)
    return {
        "methodology_version": METHODOLOGY_VERSION,
        "dimension_weights": {d.value: w for d, w in DIMENSION_WEIGHTS.items()},
        "notes": (
            "Deterministic risk-weighted coverage. Placement requires an active decoy; unknown "
            "inventory is reported separately and never counted as covered; GPT does not score."
        ),
    }


@router.get("/coverage/policy")
def get_policy(
    auth: AuthContext = Depends(require_scope("coverage:read")),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    settings = get_settings()
    _require_enabled(settings)
    import json

    record = CoverageRepository(session).get_policy(auth.organization_id)
    if record is None:
        return {"policy_version": 0}
    return {"policy_version": record.policy_version, **json.loads(record.data or "{}")}


@router.put("/coverage/policy")
def update_policy(
    body: PolicyBody, request: Request,
    auth: AuthContext = Depends(require_scope("coverage:manage_policy")),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    settings = get_settings()
    _require_enabled(settings)
    repo = CoverageRepository(session)
    doc = CoveragePolicyDoc(
        organization_id=str(auth.organization_id),
        minimum_acceptable_score=body.minimum_acceptable_score,
        minimum_sensor_health=body.minimum_sensor_health,
        verification_freshness_hours=body.verification_freshness_hours,
        maximum_unknown_weight=body.maximum_unknown_weight,
        recommendation_risk_tolerance=body.recommendation_risk_tolerance,
    )
    record = repo.upsert_policy(auth.organization_id, doc)
    repo.add_audit(
        organization_id=auth.organization_id, actor_id=auth.key_id, event_type="policy_updated",
        request_id=_request_id(request), safe_metadata=f"version={record.policy_version}",
    )
    return {"policy_version": record.policy_version}
