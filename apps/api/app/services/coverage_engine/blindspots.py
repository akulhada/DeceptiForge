# Purpose: deterministic blind-spot (coverage gap) detection.
# Responsibilities: from each surface's computed coverage + observed controls, derive explainable
#   gaps (no decoy, decoy without sensor, unhealthy/failed sensor, expired-not-replaced, fragile
#   single control, no cross-surface), each with severity and an expected coverage gain. Bounded and
#   deterministic. Dependencies: coverage domain, formula, inventory.
from __future__ import annotations

from app.models.domain.coverage import (
    ControlStatus,
    ControlType,
    CoverageDimension,
    CoverageGapModel,
    GapType,
    SurfaceCoverage,
    SurfaceType,
)
from app.models.domain.operations import Severity
from app.services.coverage_engine.inventory import SurfaceObservation

_NO_DECOY_GAP: dict[SurfaceType, GapType] = {
    SurfaceType.REPOSITORY: GapType.NO_DECOY,
    SurfaceType.DATABASE: GapType.NO_HONEY_RECORDS,
    SurfaceType.RAG: GapType.NO_RAG_TRIPWIRE,
    SurfaceType.MCP: GapType.NO_MCP_TRIPWIRE,
    SurfaceType.BROWSER_AI: GapType.SHADOW_AI_NO_POLICY,
    SurfaceType.AI_AGENT: GapType.AGENT_NO_SCOPE_POLICY,
}


def _severity(criticality: float) -> Severity:
    if criticality >= 0.8:
        return Severity.CRITICAL
    if criticality >= 0.6:
        return Severity.HIGH
    if criticality >= 0.4:
        return Severity.MEDIUM
    return Severity.LOW


def _has_active(controls, control_type: ControlType) -> bool:  # type: ignore[no-untyped-def]
    return any(
        c.control_type == control_type and c.status == ControlStatus.ACTIVE for c in controls
    )


def detect_gaps(
    coverage: SurfaceCoverage, obs: SurfaceObservation
) -> list[CoverageGapModel]:
    surface = coverage.surface
    controls = obs.controls
    gaps: list[CoverageGapModel] = []
    sev = _severity(surface.criticality)
    ext = surface.external_or_resource_id
    # Potential gain scales with the surface's risk weight (bounded to [0,1]).
    gain = min(1.0, surface.risk_weight)

    active_decoy = any(
        c.control_type == ControlType.DECOY
        and c.dimension == CoverageDimension.PLACEMENT
        and c.status == ControlStatus.ACTIVE
        for c in controls
    )
    active_sensor = _has_active(controls, ControlType.SENSOR)
    has_expired = any(c.status == ControlStatus.EXPIRED for c in controls)
    has_failed = any(c.status == ControlStatus.FAILED for c in controls)
    has_degraded = any(c.status == ControlStatus.DEGRADED for c in controls)

    if not active_decoy:
        if has_expired:
            gaps.append(CoverageGapModel(
                surface_type=surface.surface_type, external_or_resource_id=ext,
                gap_type=GapType.EXPIRED_NOT_REPLACED, severity=sev,
                reason="A decoy on this surface expired and has not been replaced.",
                missing_controls=("decoy",), expected_coverage_gain=gain,
            ))
        else:
            gaps.append(CoverageGapModel(
                surface_type=surface.surface_type, external_or_resource_id=ext,
                gap_type=_NO_DECOY_GAP[surface.surface_type], severity=sev,
                reason="No active decoy on this surface; interaction cannot be baited.",
                missing_controls=("decoy", "sensor"), expected_coverage_gain=gain,
            ))
    elif not active_sensor:
        gaps.append(CoverageGapModel(
            surface_type=surface.surface_type, external_or_resource_id=ext,
            gap_type=GapType.DECOY_NO_SENSOR, severity=sev,
            reason="A decoy is deployed but no active sensor can detect interaction.",
            missing_controls=("sensor",), expected_coverage_gain=gain * 0.7,
        ))

    if has_failed:
        gaps.append(CoverageGapModel(
            surface_type=surface.surface_type, external_or_resource_id=ext,
            gap_type=GapType.MONITORING_ACTIVATION_FAILED, severity=sev,
            reason="A control failed (verification/activation); it provides no detection.",
            missing_controls=("monitoring",), expected_coverage_gain=gain * 0.6,
        ))
    if has_degraded:
        gaps.append(CoverageGapModel(
            surface_type=surface.surface_type, external_or_resource_id=ext,
            gap_type=GapType.SENSOR_UNHEALTHY, severity=sev,
            reason="A sensor is degraded/stale; detection reliability is reduced.",
            missing_controls=("monitoring",), expected_coverage_gain=gain * 0.4,
        ))

    if active_decoy and coverage.control_diversity <= 1 and surface.criticality >= 0.6:
        gaps.append(CoverageGapModel(
            surface_type=surface.surface_type, external_or_resource_id=ext,
            gap_type=GapType.FRAGILE_SINGLE_CONTROL, severity=Severity.MEDIUM,
            reason="High-value surface relies on a single fragile control (no defense in depth).",
            missing_controls=("sensor", "monitoring"), expected_coverage_gain=gain * 0.3,
        ))
    if (
        active_decoy
        and coverage.dimension_scores.get(CoverageDimension.CROSS_SURFACE, 0.0) == 0.0
        and surface.criticality >= 0.7
    ):
        gaps.append(CoverageGapModel(
            surface_type=surface.surface_type, external_or_resource_id=ext,
            gap_type=GapType.NO_CROSS_SURFACE, severity=Severity.LOW,
            reason="Activity on this surface cannot be correlated across other surfaces.",
            missing_controls=("cross_surface",), expected_coverage_gain=gain * 0.2,
        ))
    return gaps
