# Purpose: deterministic scoring primitives for the coverage engine.
# Responsibilities: normalize surface criticality/risk from sensitivity/business/exposure/attack
#   inputs, derive control effectiveness from status/age/verification (not quantity), and compute
#   inventory/coverage confidence from freshness and measured-vs-inferred signals. Fully
#   deterministic — GPT never contributes. Pure. Dependencies: coverage domain.
from __future__ import annotations

from datetime import datetime, timedelta

from app.models.domain.coverage import ControlStatus


def clamp(value: float) -> float:
    return 0.0 if value < 0 else 1.0 if value > 1 else value


def criticality(
    *, sensitivity: float, business_impact: float, exposure: float, attack_likelihood: float
) -> float:
    """Weighted, normalized surface criticality in [0,1]. Sensitivity and business impact dominate;
    exposure and attacker likelihood modulate."""
    return clamp(
        0.35 * clamp(sensitivity)
        + 0.30 * clamp(business_impact)
        + 0.20 * clamp(exposure)
        + 0.15 * clamp(attack_likelihood)
    )


def risk_weight(crit: float, coverage_requirement: float) -> float:
    """Risk weight used to aggregate surface coverage. Higher criticality and a stricter coverage
    requirement raise the weight, so high-risk surfaces dominate the overall score."""
    return round(clamp(crit) * (0.5 + 0.5 * clamp(coverage_requirement)), 6)


# Base effectiveness ceiling per control status. A failed/expired control earns no credit.
_STATUS_CEILING: dict[ControlStatus, float] = {
    ControlStatus.ACTIVE: 1.0,
    ControlStatus.DEGRADED: 0.5,
    ControlStatus.INACTIVE: 0.0,
    ControlStatus.EXPIRED: 0.0,
    ControlStatus.FAILED: 0.0,
}


def control_effectiveness(
    *,
    status: ControlStatus,
    believability: float,
    verified_at: datetime | None,
    now: datetime,
    verification_max_age_hours: int,
    detections: int = 0,
) -> float:
    """Deterministic effectiveness in [0,1]. Quantity is never a factor — a single strong, verified
    control beats many stale ones. Stale verification decays the score."""
    ceiling = _STATUS_CEILING[status]
    if ceiling == 0.0:
        return 0.0
    base = 0.5 + 0.3 * clamp(believability)
    if verified_at is not None:
        age = now - (verified_at if verified_at.tzinfo else verified_at.replace(tzinfo=now.tzinfo))
        fresh = 1.0 if age <= timedelta(hours=verification_max_age_hours) else 0.4
        base += 0.2 * fresh
    else:
        base += 0.0  # unverified -> no verification credit
    # A small, bounded bump for real historical detections (proven signal), capped.
    base += min(0.1, detections * 0.02)
    return round(clamp(base) * ceiling, 6)


def inventory_confidence(
    *, measured: bool, freshness_hours: float, metadata_completeness: float
) -> float:
    """Confidence that the inventory entry reflects reality. Measured beats inferred; stale and
    incomplete metadata lower confidence."""
    base = 0.9 if measured else 0.5
    freshness = 1.0 if freshness_hours <= 24 else 0.7 if freshness_hours <= 168 else 0.4
    return round(clamp(base * (0.5 + 0.3 * freshness + 0.2 * clamp(metadata_completeness))), 6)


def aggregate_confidence(surface_confidences: list[float], unknown_ratio: float) -> float:
    """Overall confidence lowers as unknown inventory grows and as per-surface confidence drops."""
    if not surface_confidences:
        return 0.0
    mean = sum(surface_confidences) / len(surface_confidences)
    return round(clamp(mean * (1.0 - 0.5 * clamp(unknown_ratio))), 6)


def diversity_bonus(control_diversity: int) -> float:
    """A small resilience bonus for control-type diversity (defense in depth), bounded so it can
    never turn an uncovered surface into a covered one."""
    return min(0.1, max(0, control_diversity - 1) * 0.05)
