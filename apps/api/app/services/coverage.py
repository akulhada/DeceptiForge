# Purpose: compute a lightweight, weighted deception-coverage estimate for the demo.
# Responsibilities: turn the aggregate demo state (plus whether a narrative exists) into per-
#   dimension 0..1 signals and a weighted overall. This is intentionally simple demo logic, not a
#   full Coverage Engine. Dependencies: the demo schema.
# FUTURE_HARDENING: replace with a real Coverage Engine that measures protected surfaces against
#   discovered attack surface, decoy freshness, and monitor health over time.
from __future__ import annotations

from app.schemas.demo import CoverageSummary, DemoState

_WEIGHTS: dict[str, float] = {
    "repository": 0.15,
    "placement": 0.15,
    "decoy_activation": 0.20,
    "monitoring": 0.15,
    "alerting": 0.10,
    "incident": 0.15,
    "ai_narrative": 0.10,
}


class CoverageEngine:
    """Deterministic, demo-grade coverage estimator."""

    def compute(self, state: DemoState, *, narrative_present: bool) -> CoverageSummary:
        overview = state.overview
        repository = 1.0 if state.profile is not None and state.profile.file_count > 0 else 0.0
        placement = (
            1.0
            if state.placement_plan is not None and state.placement_plan.recommendations
            else 0.0
        )
        decoy_activation = (
            overview.accepted_decoys / overview.total_decoys if overview.total_decoys else 0.0
        )
        monitoring = 1.0 if overview.monitor_events > 0 else 0.0
        alerting = 1.0 if overview.alerts > 0 else 0.0
        incident = 1.0 if overview.incidents > 0 else 0.0
        ai_narrative = 1.0 if narrative_present else 0.0

        dimensions = {
            "repository": repository,
            "placement": placement,
            "decoy_activation": decoy_activation,
            "monitoring": monitoring,
            "alerting": alerting,
            "incident": incident,
            "ai_narrative": ai_narrative,
        }
        overall = round(sum(dimensions[key] * weight for key, weight in _WEIGHTS.items()), 4)
        return CoverageSummary(overall=overall, **dimensions)
