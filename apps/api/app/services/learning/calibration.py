# Purpose: deterministic, explainable statistical calibration over learning events.
# Responsibilities: decide which outcomes may count as effectiveness evidence (attribution),
#   aggregate per-cohort rates with Laplace smoothing and Wilson intervals, enforce minimum-sample
#   and anti-poisoning thresholds, and emit CANDIDATE weights plus an explainable report. Produces
#   the same output for the same event set. Never activates anything and never touches safety rules.
# Dependencies: learning domain contracts, settings. No I/O, no cross-tenant reads.
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime

from app.models.domain.learning import (
    FEATURE_SCHEMA_VERSION,
    METHODOLOGY_VERSION,
    OPERATIONAL_OUTCOMES,
    AttributionDecision,
    CalibrationMetrics,
    CalibrationReport,
    CalibrationWeights,
    CohortMetric,
    OutcomeType,
)

# Laplace (add-k) smoothing keeps a 1/1 cohort from reading as a certain 100%.
_LAPLACE_ALPHA = 1.0
_LAPLACE_BETA = 1.0
_Z = 1.96  # 95% Wilson interval


@dataclass(frozen=True)
class OutcomeObservation:
    """One attributable outcome. Carries no raw content — cohort labels are categories."""

    cohort: str
    outcome_type: OutcomeType
    actor_id: str | None
    observation_hours: float
    healthy_monitoring_ratio: float
    predicted_confidence: float


def wilson_interval(successes: int, total: int, z: float = _Z) -> tuple[float, float]:
    """Wilson score interval — honest uncertainty instead of false precision on small samples."""
    if total <= 0:
        return (0.0, 1.0)
    p = successes / total
    denom = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denom
    margin = (z / denom) * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total))
    return (round(max(0.0, center - margin), 4), round(min(1.0, center + margin), 4))


def smoothed_rate(successes: int, total: int) -> float:
    """Laplace-smoothed rate; never 0 or 1 from a single observation."""
    return round((successes + _LAPLACE_ALPHA) / (total + _LAPLACE_ALPHA + _LAPLACE_BETA), 4)


def attribute(
    observation: OutcomeObservation,
    *,
    min_observation_hours: float,
    min_healthy_monitoring_ratio: float,
) -> AttributionDecision:
    """Decide whether an outcome may be used as effectiveness evidence.

    A placement is never scored negatively for a platform failure, an unobserved window, or an
    unhealthy sensor — those explain the absence of a trigger without implicating the placement.
    """
    if observation.outcome_type in OPERATIONAL_OUTCOMES:
        return AttributionDecision(usable=False, reason_code="operational_failure")
    if observation.outcome_type is OutcomeType.NOT_TRIGGERED:
        if observation.observation_hours < min_observation_hours:
            return AttributionDecision(
                usable=False,
                reason_code="observation_window_too_short",
                observation_hours=observation.observation_hours,
                healthy_monitoring_ratio=observation.healthy_monitoring_ratio,
            )
        if observation.healthy_monitoring_ratio < min_healthy_monitoring_ratio:
            return AttributionDecision(
                usable=False,
                reason_code="monitoring_unhealthy",
                observation_hours=observation.observation_hours,
                healthy_monitoring_ratio=observation.healthy_monitoring_ratio,
            )
    return AttributionDecision(
        usable=True,
        reason_code="",
        observation_hours=observation.observation_hours,
        healthy_monitoring_ratio=observation.healthy_monitoring_ratio,
    )


def _cohort_metrics(
    observations: list[OutcomeObservation],
    positive: frozenset[OutcomeType],
    *,
    min_samples: int,
    min_distinct_actors: int,
    max_actor_contribution: float,
) -> tuple[CohortMetric, ...]:
    grouped: dict[str, list[OutcomeObservation]] = defaultdict(list)
    for obs in observations:
        grouped[obs.cohort].append(obs)

    metrics: list[CohortMetric] = []
    for cohort in sorted(grouped):  # sorted -> deterministic output
        rows = grouped[cohort]
        actors = [r.actor_id for r in rows if r.actor_id]
        distinct = len(set(actors))
        total = len(rows)
        successes = sum(1 for r in rows if r.outcome_type in positive)
        low, high = wilson_interval(successes, total)

        # Anti-poisoning: a cohort is only "sufficient" with enough samples, enough distinct human
        # actors (when humans contributed at all), and no single actor dominating the evidence.
        dominated = False
        if actors:
            top = max(actors.count(a) for a in set(actors))
            dominated = (top / len(actors)) > max_actor_contribution
        sufficient = (
            total >= min_samples
            and not dominated
            and (distinct >= min_distinct_actors or not actors)
        )
        metrics.append(
            CohortMetric(
                cohort=cohort,
                sample_count=total,
                successes=successes,
                rate=smoothed_rate(successes, total),
                wilson_low=low,
                wilson_high=high,
                distinct_actors=distinct,
                sufficient=sufficient,
            )
        )
    return tuple(metrics)


def confidence_calibration_error(
    observations: list[OutcomeObservation], positive: frozenset[OutcomeType]
) -> float:
    """Mean absolute gap between predicted confidence and observed success rate, by 0.1 bin."""
    bins: dict[int, list[OutcomeObservation]] = defaultdict(list)
    for obs in observations:
        bins[min(9, int(obs.predicted_confidence * 10))].append(obs)
    if not bins:
        return 0.0
    total_error = 0.0
    for index in sorted(bins):
        rows = bins[index]
        observed = sum(1 for r in rows if r.outcome_type in positive) / len(rows)
        predicted = (index + 0.5) / 10
        total_error += abs(observed - predicted)
    return round(total_error / len(bins), 4)


def build_candidate(
    observations: list[OutcomeObservation],
    *,
    window_start: datetime,
    window_end: datetime,
    previous: CalibrationWeights | None,
    min_samples: int,
    min_distinct_actors: int,
    max_actor_contribution: float,
    min_observation_hours: float,
    min_healthy_monitoring_ratio: float,
) -> CalibrationReport | None:
    """Produce a candidate report, or None when the evidence is too thin to justify any change."""
    usable: list[OutcomeObservation] = []
    exclusions: dict[str, int] = defaultdict(int)
    for obs in observations:
        decision = attribute(
            obs,
            min_observation_hours=min_observation_hours,
            min_healthy_monitoring_ratio=min_healthy_monitoring_ratio,
        )
        if decision.usable:
            usable.append(obs)
        else:
            exclusions[decision.reason_code] += 1

    if len(usable) < min_samples:
        return None

    accepted = frozenset({OutcomeType.ACCEPTED, OutcomeType.DEPLOYED})
    triggered = frozenset({OutcomeType.TRIGGERED})
    acceptance = _cohort_metrics(
        usable,
        accepted,
        min_samples=min_samples,
        min_distinct_actors=min_distinct_actors,
        max_actor_contribution=max_actor_contribution,
    )
    trigger = _cohort_metrics(
        usable,
        triggered,
        min_samples=min_samples,
        min_distinct_actors=min_distinct_actors,
        max_actor_contribution=max_actor_contribution,
    )

    base = previous or CalibrationWeights()
    # Only cohorts that passed every sufficiency check may move a prior. Everything else keeps the
    # deterministic default, so thin or manipulated evidence changes nothing.
    zone_priors = dict(base.zone_priors)
    for metric in acceptance:
        if metric.sufficient:
            zone_priors[metric.cohort] = metric.rate

    metrics = CalibrationMetrics(
        acceptance=acceptance,
        trigger=trigger,
        false_positive=(),
        confidence_calibration_error=confidence_calibration_error(usable, accepted),
        included_event_count=len(usable),
        excluded_event_count=sum(exclusions.values()),
        exclusion_reasons=dict(sorted(exclusions.items())),
    )
    candidate = CalibrationWeights(
        zone_priors=dict(sorted(zone_priors.items())),
        decoy_type_priors=dict(base.decoy_type_priors),
        confidence_scale=base.confidence_scale,
        evidence_strength=base.evidence_strength,
        tie_breaker=base.tie_breaker,
    )
    limitations: list[str] = []
    insufficient = [m.cohort for m in acceptance if not m.sufficient]
    if insufficient:
        limitations.append(
            f"{len(insufficient)} cohort(s) below the sufficiency threshold kept defaults"
        )
    if metrics.excluded_event_count:
        limitations.append(
            f"{metrics.excluded_event_count} outcome(s) excluded by attribution rules"
        )
    return CalibrationReport(
        methodology_version=METHODOLOGY_VERSION,
        feature_schema_version=FEATURE_SCHEMA_VERSION,
        training_window_start=window_start,
        training_window_end=window_end,
        included_event_count=len(usable),
        excluded_event_count=metrics.excluded_event_count,
        exclusion_reasons=metrics.exclusion_reasons,
        previous_weights=previous,
        candidate_weights=candidate,
        metrics=metrics,
        safety_constraints_preserved=True,
        known_limitations=tuple(limitations)[:10],
    )
