# Purpose: apply an approved, active calibration to deterministic placement results.
# Responsibilities: adjust ONLY confidence and ordering using reviewed priors, re-rank stably, and
#   emit a structured "why this changed" explanation per recommendation. The zone, proposed path,
#   decoy type, and deployment risk are copied through untouched, so calibration can never move a
#   safety decision. A no-op (no active version, or no prior for a cohort) still returns an
#   explanation stating why nothing changed. Dependencies: learning + preview contracts. No I/O.
from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from app.models.domain.analysis_preview import PlacementRecommendationView
from app.models.domain.learning import (
    CalibrationWeights,
    RecommendationChangeExplanation,
)

# Hard bounds on how far a reviewed prior may move a deterministic confidence.
_MIN_FACTOR = 0.75
_MAX_FACTOR = 1.25


@dataclass(frozen=True)
class ActiveCalibration:
    """The approved, active calibration for one organization (or none)."""

    model_version_id: UUID | None = None
    weights: CalibrationWeights | None = None
    organization_specific: bool = False
    global_aggregate_used: bool = False
    # Evidence behind each cohort prior, used only to explain a change honestly.
    cohort_samples: dict[str, int] = field(default_factory=dict)
    cohort_intervals: dict[str, tuple[float, float]] = field(default_factory=dict)

    @property
    def active(self) -> bool:
        return self.model_version_id is not None and self.weights is not None


def _factor(prior: float, confidence_scale: float) -> float:
    """Map a 0..1 prior onto a bounded multiplier, then apply the reviewed confidence scale."""
    raw = (_MIN_FACTOR + (_MAX_FACTOR - _MIN_FACTOR) * prior) * confidence_scale
    return max(_MIN_FACTOR, min(_MAX_FACTOR, raw))


def apply_calibration(
    recommendations: tuple[PlacementRecommendationView, ...],
    calibration: ActiveCalibration,
) -> tuple[tuple[PlacementRecommendationView, ...], tuple[RecommendationChangeExplanation, ...]]:
    """Return (possibly re-ranked recommendations, one explanation per recommendation)."""
    if not recommendations:
        return (), ()

    if not calibration.active or calibration.weights is None:
        # Deterministic baseline in effect — say so rather than implying a calibrated result.
        baseline = tuple(
            RecommendationChangeExplanation(
                active_model_version=None,
                changed=False,
                previous_confidence=item.confidence,
                current_confidence=item.confidence,
                previous_rank=item.rank,
                current_rank=item.rank,
                sample_count=0,
                explanation=(
                    "No active calibration for this organization; the deterministic baseline "
                    "produced this result."
                ),
            )
            for item in recommendations
        )
        return recommendations, baseline

    weights = calibration.weights
    adjusted: list[tuple[PlacementRecommendationView, float]] = []
    for item in recommendations:
        prior = weights.zone_priors.get(item.zone)
        if prior is None:
            adjusted.append((item, item.confidence))
            continue
        new_confidence = round(
            max(0.0, min(1.0, item.confidence * _factor(prior, weights.confidence_scale))), 4
        )
        adjusted.append((item, new_confidence))

    # Stable deterministic ordering: confidence desc, then the original path for ties.
    ordered = sorted(adjusted, key=lambda pair: (-pair[1], pair[0].proposed_path_or_pattern))

    results: list[PlacementRecommendationView] = []
    explanations: list[RecommendationChangeExplanation] = []
    for new_rank, (item, new_confidence) in enumerate(ordered, start=1):
        prior = weights.zone_priors.get(item.zone)
        samples = calibration.cohort_samples.get(item.zone, 0)
        interval = calibration.cohort_intervals.get(item.zone)
        changed = new_confidence != item.confidence or new_rank != item.rank

        if prior is None:
            explanation = (
                f"Ranking and confidence are unchanged for the {item.zone} zone: the sample count "
                "is below the promotion threshold, so the deterministic default was kept."
            )
            factors: tuple[str, ...] = ()
        else:
            direction = (
                "increased"
                if new_confidence > item.confidence
                else ("reduced" if new_confidence < item.confidence else "unchanged")
            )
            explanation = (
                f"Confidence was {direction} for the {item.zone} zone because reviewed outcomes in "
                f"this organization produced an acceptance rate of {prior:.2f} across "
                f"{samples} attributable outcome(s)."
            )
            factors = ("organization_zone_prior",)

        # Safety-relevant fields are copied through unchanged; only confidence/rank may move.
        results.append(item.model_copy(update={"rank": new_rank, "confidence": new_confidence}))
        explanations.append(
            RecommendationChangeExplanation(
                active_model_version=calibration.model_version_id,
                changed=changed,
                changed_factors=factors,
                previous_confidence=item.confidence,
                current_confidence=new_confidence,
                previous_rank=item.rank,
                current_rank=new_rank,
                sample_count=samples,
                confidence_interval=interval,
                organization_specific=calibration.organization_specific,
                global_aggregate_used=calibration.global_aggregate_used,
                explanation=explanation[:512],
            )
        )
    return tuple(results), tuple(explanations)
