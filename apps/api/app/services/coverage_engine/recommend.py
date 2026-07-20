# Purpose: deterministic placement-optimization recommendations from detected gaps.
# Responsibilities: turn each gap into a ranked, explainable recommendation with expected coverage/
#   detection gain, deployment + false-positive risk, effort, and a priority score; filter unsafe or
#   redundant recommendations; and bound the output. Recommendations are advisory — accepting one
#   creates a deployment draft only, never an automatic deployment. Deterministic; GPT never scores.
# Dependencies: coverage domain.
from __future__ import annotations

from app.models.domain.coverage import (
    CoverageGapModel,
    GapType,
    RecommendationModel,
    RecommendedAction,
    SurfaceCoverage,
    SurfaceType,
)
from app.services.coverage_engine import scoring

_ACTION: dict[GapType, RecommendedAction] = {
    GapType.NO_DECOY: RecommendedAction.ADD_DECOY,
    GapType.NO_HONEY_RECORDS: RecommendedAction.ADD_DECOY,
    GapType.NO_RAG_TRIPWIRE: RecommendedAction.ADD_DECOY,
    GapType.NO_MCP_TRIPWIRE: RecommendedAction.ADD_DECOY,
    GapType.SHADOW_AI_NO_POLICY: RecommendedAction.ADD_BROWSER_POLICY,
    GapType.AGENT_NO_SCOPE_POLICY: RecommendedAction.ADD_AGENT_SCOPE_POLICY,
    GapType.DECOY_NO_SENSOR: RecommendedAction.ADD_SENSOR,
    GapType.EXPIRED_NOT_REPLACED: RecommendedAction.REPLACE_EXPIRED,
    GapType.MONITORING_ACTIVATION_FAILED: RecommendedAction.REPAIR_SENSOR,
    GapType.SENSOR_UNHEALTHY: RecommendedAction.REPAIR_SENSOR,
    GapType.FRAGILE_SINGLE_CONTROL: RecommendedAction.DIVERSIFY_CONTROLS,
    GapType.NO_CROSS_SURFACE: RecommendedAction.DIVERSIFY_CONTROLS,
}

_DECOY_TYPE: dict[SurfaceType, str] = {
    SurfaceType.REPOSITORY: "repository_decoy",
    SurfaceType.DATABASE: "honey_record",
    SurfaceType.RAG: "rag_document",
    SurfaceType.MCP: "mcp_resource",
    SurfaceType.BROWSER_AI: "browser_policy",
    SurfaceType.AI_AGENT: "agent_scope_policy",
}

# Base deployment risk / effort per surface type (deterministic, connector-aware defaults).
_DEPLOY_RISK: dict[SurfaceType, float] = {
    SurfaceType.REPOSITORY: 0.3,
    SurfaceType.DATABASE: 0.5,
    SurfaceType.RAG: 0.35,
    SurfaceType.MCP: 0.35,
    SurfaceType.BROWSER_AI: 0.2,
    SurfaceType.AI_AGENT: 0.2,
}


def _recommendation(
    gap: CoverageGapModel, coverage: SurfaceCoverage, risk_tolerance: float
) -> RecommendationModel | None:
    surface = coverage.surface
    action = _ACTION[gap.gap_type]
    deploy_risk = _DEPLOY_RISK[surface.surface_type]
    fp_risk = 0.2 if surface.surface_type in (SurfaceType.DATABASE, SurfaceType.RAG) else 0.15
    heavy = action in (RecommendedAction.ADD_DECOY, RecommendedAction.REPLACE_EXPIRED)
    effort = 0.4 if heavy else 0.3
    coverage_gain = gap.expected_coverage_gain
    detection_factor = 0.8 if action == RecommendedAction.ADD_SENSOR else 1.0
    detection_gain = scoring.clamp(coverage_gain * detection_factor)

    # Constraint: filter unsafe/low-benefit — high deployment risk with low expected benefit, or
    # risk beyond the organization's tolerance.
    if deploy_risk > risk_tolerance and coverage_gain < 0.3:
        return None
    if coverage_gain <= 0.0:
        return None

    # Deterministic priority: surface risk x expected gain x detection, penalized by risk + effort.
    priority = round(
        surface.risk_weight * (0.6 * coverage_gain + 0.4 * detection_gain)
        * (1.0 - 0.4 * deploy_risk - 0.2 * effort),
        6,
    )
    if priority <= 0:
        return None
    return RecommendationModel(
        surface_type=surface.surface_type, external_or_resource_id=surface.external_or_resource_id,
        recommended_action=action, recommended_decoy_type=_DECOY_TYPE[surface.surface_type],
        target_location=surface.display_name, expected_coverage_gain=coverage_gain,
        expected_detection_gain=detection_gain, deployment_risk=deploy_risk,
        false_positive_risk=fp_risk, implementation_effort=effort, priority_score=priority,
        confidence=surface.inventory_confidence,
        explanation=(
            f"{action.value} on {surface.display_name}: +{coverage_gain:.2f} coverage, "
            f"+{detection_gain:.2f} detection, risk {deploy_risk:.2f}, effort {effort:.2f}."
        ),
    )


def build_recommendations(
    gaps_by_surface: list[tuple[SurfaceCoverage, list[CoverageGapModel]]],
    *,
    risk_tolerance: float,
    max_recommendations: int,
) -> list[RecommendationModel]:
    recs: list[RecommendationModel] = []
    seen: set[tuple[str, str]] = set()  # (surface ext id, action) -> dedupe, no redundant gain
    for coverage, gaps in gaps_by_surface:
        for gap in gaps:
            rec = _recommendation(gap, coverage, risk_tolerance)
            if rec is None:
                continue
            key = (rec.external_or_resource_id, rec.recommended_action.value)
            if key in seen:
                continue  # duplicate action on the same surface adds no incremental gain
            seen.add(key)
            recs.append(rec)
    recs.sort(key=lambda r: r.priority_score, reverse=True)
    return recs[:max_recommendations]
