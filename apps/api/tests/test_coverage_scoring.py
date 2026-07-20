# Purpose: verify deterministic coverage scoring primitives — criticality, risk weight, control
#   effectiveness (quantity-agnostic, verification decay), and confidence.
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.models.domain.coverage import ControlStatus
from app.services.coverage_engine import scoring

_NOW = datetime(2026, 7, 19, tzinfo=UTC)


def test_criticality_weighted_and_bounded() -> None:
    high = scoring.criticality(
        sensitivity=1.0, business_impact=1.0, exposure=1.0, attack_likelihood=1.0
    )
    low = scoring.criticality(
        sensitivity=0.0, business_impact=0.0, exposure=0.0, attack_likelihood=0.0
    )
    assert high == pytest.approx(1.0) and low == 0.0
    assert 0.0 <= scoring.criticality(
        sensitivity=0.8, business_impact=0.5, exposure=0.4, attack_likelihood=0.6
    ) <= 1.0


def test_risk_weight_increases_with_criticality() -> None:
    assert scoring.risk_weight(0.9, 1.0) > scoring.risk_weight(0.2, 1.0)


def test_failed_and_expired_controls_earn_nothing() -> None:
    for status in (ControlStatus.FAILED, ControlStatus.EXPIRED, ControlStatus.INACTIVE):
        assert scoring.control_effectiveness(
            status=status, believability=1.0, verified_at=_NOW, now=_NOW,
            verification_max_age_hours=168,
        ) == 0.0


def test_verification_freshness_decays_effectiveness() -> None:
    fresh = scoring.control_effectiveness(
        status=ControlStatus.ACTIVE, believability=0.7, verified_at=_NOW - timedelta(hours=1),
        now=_NOW, verification_max_age_hours=168,
    )
    stale = scoring.control_effectiveness(
        status=ControlStatus.ACTIVE, believability=0.7,
        verified_at=_NOW - timedelta(hours=1000), now=_NOW, verification_max_age_hours=168,
    )
    assert fresh > stale


def test_effectiveness_is_quantity_agnostic() -> None:
    # One strong verified control on a surface beats the *per-control* score regardless of count;
    # effectiveness is a per-control property, never summed here.
    strong = scoring.control_effectiveness(
        status=ControlStatus.ACTIVE, believability=0.9, verified_at=_NOW, now=_NOW,
        verification_max_age_hours=168, detections=3,
    )
    weak = scoring.control_effectiveness(
        status=ControlStatus.ACTIVE, believability=0.1, verified_at=None, now=_NOW,
        verification_max_age_hours=168,
    )
    assert strong > weak
    assert strong <= 1.0


def test_confidence_measured_beats_inferred_and_stale_lowers() -> None:
    measured = scoring.inventory_confidence(
        measured=True, freshness_hours=1, metadata_completeness=1.0
    )
    inferred = scoring.inventory_confidence(
        measured=False, freshness_hours=1, metadata_completeness=1.0
    )
    stale = scoring.inventory_confidence(
        measured=True, freshness_hours=1000, metadata_completeness=1.0
    )
    assert measured > inferred
    assert measured > stale


def test_aggregate_confidence_lowers_with_unknown() -> None:
    low_unknown = scoring.aggregate_confidence([0.9, 0.9], 0.0)
    high_unknown = scoring.aggregate_confidence([0.9, 0.9], 0.8)
    assert low_unknown > high_unknown


def test_diversity_bonus_bounded() -> None:
    assert scoring.diversity_bonus(1) == 0.0
    assert scoring.diversity_bonus(10) <= 0.1
