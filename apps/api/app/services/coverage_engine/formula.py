# Purpose: the versioned, deterministic coverage formula.
# Responsibilities: reduce a surface's observed controls to per-dimension scores, combine them with
#   fixed dimension weights into a surface coverage in [0,1], risk-weight it, and mark unknown
#   surfaces. Placement requires an active decoy (a sensor alone is not placement coverage).
#   Deterministic; GPT never scores. Pure. Dependencies: coverage domain, scoring, inventory.
from __future__ import annotations

from app.models.domain.coverage import (
    ControlStatus,
    CoverageDimension,
    SurfaceControl,
    SurfaceCoverage,
)
from app.services.coverage_engine import scoring
from app.services.coverage_engine.inventory import SurfaceObservation

# Fixed dimension weights (sum to 1.0). Bump METHODOLOGY_VERSION if these change.
DIMENSION_WEIGHTS: dict[CoverageDimension, float] = {
    CoverageDimension.PLACEMENT: 0.22,
    CoverageDimension.SENSOR: 0.20,
    CoverageDimension.HEALTH: 0.16,
    CoverageDimension.ALERTING: 0.10,
    CoverageDimension.INCIDENT: 0.08,
    CoverageDimension.LIFECYCLE: 0.08,
    CoverageDimension.IDENTITY: 0.06,
    CoverageDimension.VERIFICATION: 0.06,
    CoverageDimension.CROSS_SURFACE: 0.04,
}

# Inventory below this confidence is "unknown" — reported separately, never counted as covered.
_UNKNOWN_CONFIDENCE_FLOOR = 0.4


def _dimension_score(controls: list[SurfaceControl], dimension: CoverageDimension) -> float:
    """Best active control in a dimension. A dimension with no active control scores 0."""
    best = 0.0
    for c in controls:
        if c.dimension == dimension and c.status == ControlStatus.ACTIVE:
            best = max(best, c.effectiveness_score)
    return best


def compute_surface_coverage(
    obs: SurfaceObservation, *, cross_surface_present: bool
) -> SurfaceCoverage:
    controls = obs.controls
    scores: dict[CoverageDimension, float] = {}
    for dimension in CoverageDimension:
        if dimension == CoverageDimension.CROSS_SURFACE:
            scores[dimension] = 1.0 if cross_surface_present else 0.0
            continue
        scores[dimension] = _dimension_score(controls, dimension)

    # Placement gate: no active decoy -> placement is 0 and caps nothing else, but downstream
    # detection dimensions still reflect that a sensor without a decoy is not placement coverage.
    placement = scores[CoverageDimension.PLACEMENT]
    base = sum(scores[d] * DIMENSION_WEIGHTS[d] for d in CoverageDimension)

    active = [c for c in controls if c.status == ControlStatus.ACTIVE]
    diversity = len({c.control_type for c in active})
    # Diversity is a small, bounded resilience bonus and can never turn a 0-placement surface into
    # covered — it only applies once real placement exists.
    bonus = scoring.diversity_bonus(diversity) if placement > 0 else 0.0
    surface_coverage = scoring.clamp(base + bonus)

    is_unknown = obs.surface.inventory_confidence < _UNKNOWN_CONFIDENCE_FLOOR
    weighted = 0.0 if is_unknown else round(surface_coverage * obs.surface.risk_weight, 6)

    explanation = (
        f"placement {placement:.2f}, sensor {scores[CoverageDimension.SENSOR]:.2f}, "
        f"health {scores[CoverageDimension.HEALTH]:.2f}, "
        f"diversity {diversity} -> coverage {surface_coverage:.2f}"
        + (" (unknown: low inventory confidence)" if is_unknown else "")
    )
    return SurfaceCoverage(
        surface=obs.surface, dimension_scores=scores, surface_coverage=surface_coverage,
        weighted_coverage=weighted, confidence=obs.surface.inventory_confidence,
        is_unknown=is_unknown, control_count=len(controls), control_diversity=diversity,
        explanation=explanation,
    )
