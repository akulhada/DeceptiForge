# Purpose: verify the learning boundary — data minimization, outcome attribution, anti-poisoning
#   thresholds, deterministic candidate generation, and the reviewed version lifecycle.
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.models.domain.learning import (
    FEATURE_SCHEMA_VERSION,
    Bucket,
    CalibrationWeights,
    ModelScope,
    ModelStatus,
    NormalizedFeatures,
    OutcomeType,
    bucket_of,
    transition_allowed,
)
from app.services.learning.calibration import (
    OutcomeObservation,
    attribute,
    build_candidate,
    smoothed_rate,
    wilson_interval,
)
from app.services.learning.features import (
    MinimizationError,
    assert_minimized,
    feature_hash,
    source_id_hash,
)
from app.services.learning.versions import (
    VersionTransitionError,
    VersionView,
    activate,
    approve,
    rollback,
)

WINDOW_START = datetime(2026, 1, 1, tzinfo=UTC)
WINDOW_END = WINDOW_START + timedelta(days=30)


# ---- data minimization ---------------------------------------------------------------------------


def test_minimization_rejects_paths_and_secrets() -> None:
    for bad in ("src/payment/service.py", "config.yaml", "https://x.example", "AWS_SECRET_KEY"):
        with pytest.raises(MinimizationError):
            assert_minimized(NormalizedFeatures(dominant_language_category=bad))


def test_minimization_rejects_opaque_blob_and_pem() -> None:
    with pytest.raises(MinimizationError):
        assert_minimized(NormalizedFeatures(business_domain_category="A" * 45))
    with pytest.raises(MinimizationError):
        assert_minimized(NormalizedFeatures(repository_architecture="-----BEGIN RSA"))


def test_minimization_accepts_plain_categories() -> None:
    ok = assert_minimized(
        NormalizedFeatures(
            dominant_language_category="python",
            business_domain_category="fintech",
            sensitive_zone_categories=("payment", "secrets_and_credentials"),
        )
    )
    assert ok.business_domain_category == "fintech"


def test_counts_are_bucketed_not_raw() -> None:
    assert bucket_of(0) is Bucket.NONE
    assert bucket_of(1) is Bucket.LOW
    assert bucket_of(4) is Bucket.MEDIUM
    assert bucket_of(500) is Bucket.VERY_HIGH


def test_feature_hash_is_stable_and_source_hash_is_org_salted() -> None:
    features = NormalizedFeatures(business_domain_category="fintech")
    assert feature_hash(features) == feature_hash(features)
    org_a, org_b = str(uuid4()), str(uuid4())
    # Same source identifier in two tenants must not produce a linkable hash.
    assert source_id_hash(org_a, "repo-1") != source_id_hash(org_b, "repo-1")


def test_feature_contract_has_no_free_text_field() -> None:
    # Reviewability: every field is an enum, bucket, score, or bounded category tuple.
    for name in NormalizedFeatures.model_fields:
        assert "comment" not in name and "path" not in name and "content" not in name


# ---- outcome attribution -------------------------------------------------------------------------


def _obs(
    outcome: OutcomeType,
    *,
    hours: float = 200,
    health: float = 1.0,
    actor: str | None = None,
    confidence: float = 0.8,
    cohort: str = "payment",
) -> OutcomeObservation:
    return OutcomeObservation(
        cohort=cohort,
        outcome_type=outcome,
        actor_id=actor,
        observation_hours=hours,
        healthy_monitoring_ratio=health,
        predicted_confidence=confidence,
    )


def test_operational_failure_is_not_placement_evidence() -> None:
    for outcome in (OutcomeType.DEPLOYMENT_FAILED, OutcomeType.ROLLED_BACK):
        decision = attribute(
            _obs(outcome), min_observation_hours=72, min_healthy_monitoring_ratio=0.8
        )
        assert decision.usable is False
        assert decision.reason_code == "operational_failure"


def test_not_triggered_excluded_when_window_too_short_or_monitoring_unhealthy() -> None:
    short = attribute(
        _obs(OutcomeType.NOT_TRIGGERED, hours=1),
        min_observation_hours=72,
        min_healthy_monitoring_ratio=0.8,
    )
    assert short.usable is False and short.reason_code == "observation_window_too_short"
    unhealthy = attribute(
        _obs(OutcomeType.NOT_TRIGGERED, health=0.2),
        min_observation_hours=72,
        min_healthy_monitoring_ratio=0.8,
    )
    assert unhealthy.usable is False and unhealthy.reason_code == "monitoring_unhealthy"


def test_not_triggered_counts_when_window_and_health_satisfied() -> None:
    decision = attribute(
        _obs(OutcomeType.NOT_TRIGGERED, hours=200, health=1.0),
        min_observation_hours=72,
        min_healthy_monitoring_ratio=0.8,
    )
    assert decision.usable is True


# ---- statistics ----------------------------------------------------------------------------------


def test_smoothing_prevents_certainty_from_one_sample() -> None:
    assert 0.0 < smoothed_rate(1, 1) < 1.0
    assert 0.0 < smoothed_rate(0, 1) < 1.0


def test_wilson_widens_on_small_samples() -> None:
    low_small, high_small = wilson_interval(1, 2)
    low_big, high_big = wilson_interval(50, 100)
    assert (high_small - low_small) > (high_big - low_big)


# ---- calibration + anti-poisoning ----------------------------------------------------------------


def _build(observations: list[OutcomeObservation], **kw):  # type: ignore[no-untyped-def]
    params = dict(
        window_start=WINDOW_START,
        window_end=WINDOW_END,
        previous=None,
        min_samples=5,
        min_distinct_actors=3,
        max_actor_contribution=0.34,
        min_observation_hours=72,
        min_healthy_monitoring_ratio=0.8,
    )
    params.update(kw)
    return build_candidate(observations, **params)  # type: ignore[arg-type]


def test_insufficient_samples_produce_no_candidate() -> None:
    assert _build([_obs(OutcomeType.ACCEPTED) for _ in range(2)]) is None


def test_candidate_is_deterministic_for_the_same_event_set() -> None:
    events = [_obs(OutcomeType.ACCEPTED, actor=f"a{i%4}") for i in range(12)]
    first, second = _build(events), _build(events)
    assert first is not None and second is not None
    assert first.candidate_weights.model_dump() == second.candidate_weights.model_dump()


def test_single_actor_domination_blocks_a_prior_change() -> None:
    # One actor supplies every observation -> cohort must not be treated as sufficient.
    events = [_obs(OutcomeType.ACCEPTED, actor="solo") for _ in range(12)]
    report = _build(events)
    assert report is not None
    assert all(not m.sufficient for m in report.metrics.acceptance)
    assert report.candidate_weights.zone_priors == {}


def test_too_few_distinct_actors_blocks_a_prior_change() -> None:
    events = [_obs(OutcomeType.ACCEPTED, actor=f"a{i%2}") for i in range(12)]
    report = _build(events)
    assert report is not None
    assert all(not m.sufficient for m in report.metrics.acceptance)


def test_sufficient_diverse_evidence_moves_the_prior() -> None:
    events = [_obs(OutcomeType.ACCEPTED, actor=f"a{i%5}") for i in range(15)]
    report = _build(events)
    assert report is not None
    assert report.metrics.acceptance[0].sufficient is True
    assert "payment" in report.candidate_weights.zone_priors


def test_excluded_outcomes_are_reported_with_reasons() -> None:
    events = [_obs(OutcomeType.ACCEPTED, actor=f"a{i%5}") for i in range(10)]
    events += [_obs(OutcomeType.DEPLOYMENT_FAILED) for _ in range(4)]
    report = _build(events)
    assert report is not None
    assert report.excluded_event_count == 4
    assert report.exclusion_reasons["operational_failure"] == 4


def test_calibration_never_touches_safety_weights() -> None:
    events = [_obs(OutcomeType.ACCEPTED, actor=f"a{i%5}") for i in range(15)]
    report = _build(events, previous=CalibrationWeights(confidence_scale=1.0))
    assert report is not None
    # Only priors move; the safety-relevant scalars keep their baseline values.
    assert report.candidate_weights.confidence_scale == 1.0
    assert report.candidate_weights.evidence_strength == 1.0
    assert report.safety_constraints_preserved is True


# ---- version lifecycle ---------------------------------------------------------------------------


def _version(
    status: ModelStatus,
    *,
    org=None,
    requester=None,
    schema=FEATURE_SCHEMA_VERSION,
    safe: bool = True,
    scope: ModelScope = ModelScope.ORGANIZATION,
) -> VersionView:
    return VersionView(
        id=uuid4(),
        organization_id=org or uuid4(),
        scope=scope,
        status=status,
        feature_schema_version=schema,
        requested_by_actor_id=requester,
        safety_constraints_preserved=safe,
    )


def test_candidate_cannot_jump_to_active() -> None:
    assert transition_allowed(ModelStatus.CANDIDATE, ModelStatus.ACTIVE) is False
    assert transition_allowed(ModelStatus.REJECTED, ModelStatus.ACTIVE) is False


def test_activation_requires_approval() -> None:
    org = uuid4()
    version = _version(ModelStatus.CANDIDATE, org=org)
    with pytest.raises(VersionTransitionError):
        activate(version, organization_id=org)


def test_approved_version_activates_and_rolls_back() -> None:
    org = uuid4()
    approved = _version(ModelStatus.APPROVED, org=org)
    assert activate(approved, organization_id=org) is ModelStatus.ACTIVE
    active = _version(ModelStatus.ACTIVE, org=org)
    assert rollback(active, organization_id=org, reason="regression") is ModelStatus.ROLLED_BACK


def test_rollback_requires_a_reason() -> None:
    org = uuid4()
    with pytest.raises(VersionTransitionError):
        rollback(_version(ModelStatus.ACTIVE, org=org), organization_id=org, reason="  ")


def test_separation_of_duties_blocks_self_approval() -> None:
    org, actor = uuid4(), uuid4()
    version = _version(ModelStatus.UNDER_REVIEW, org=org, requester=actor)
    with pytest.raises(VersionTransitionError):
        approve(version, organization_id=org, approver_actor_id=actor)
    assert approve(version, organization_id=org, approver_actor_id=uuid4()) is ModelStatus.APPROVED


def test_cross_organization_activation_rejected() -> None:
    version = _version(ModelStatus.APPROVED, org=uuid4())
    with pytest.raises(VersionTransitionError):
        activate(version, organization_id=uuid4())


def test_global_scope_requires_platform_administration() -> None:
    org = uuid4()
    version = _version(ModelStatus.APPROVED, org=org, scope=ModelScope.GLOBAL)
    with pytest.raises(VersionTransitionError):
        activate(version, organization_id=org)


def test_incompatible_feature_schema_rejected() -> None:
    org = uuid4()
    version = _version(ModelStatus.APPROVED, org=org, schema="features-v0")
    with pytest.raises(VersionTransitionError):
        activate(version, organization_id=org)


def test_activation_blocked_when_safety_constraints_not_preserved() -> None:
    org = uuid4()
    version = _version(ModelStatus.APPROVED, org=org, safe=False)
    with pytest.raises(VersionTransitionError):
        activate(version, organization_id=org)
