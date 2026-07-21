# Purpose: verify engine integration — every recommendation carries its engine/model/schema version,
#   a change explanation is always present (including when nothing changed), calibration may move
#   only confidence and rank, and one organization's calibration never shapes another's result.
from __future__ import annotations

from uuid import UUID, uuid4

from app.models.domain.analysis_preview import PlacementRecommendationView
from app.models.domain.analysis_signals import RepositorySignals
from app.models.domain.learning import CalibrationWeights
from app.services.analysis_lab import AnalysisPreviewService
from app.services.learning.applied import ActiveCalibration, apply_calibration

_SERVICE = AnalysisPreviewService()
_SIGNALS = RepositorySignals.model_validate(
    {
        "services": [{"name": "payment-service"}, {"name": "ledger-api"}],
        "databases": [{"engine": "PostgreSQL", "data_domain_terms": ["payment", "settlement"]}],
        "naming_patterns": {"domain_terms": ["payment", "settlement", "reconciliation"]},
        "secret_locations": [{"path": "svc/.env.example", "category": "payment_gateway"}],
        "documentation": {"runbook_paths": ["docs/runbooks/payment.md"]},
    }
)


def _rec(zone: str, rank: int, confidence: float) -> PlacementRecommendationView:
    return PlacementRecommendationView(
        rank=rank,
        zone=zone,
        proposed_path_or_pattern=f"{zone}/.env.example",
        decoy_type="secret",
        expected_visibility=0.5,
        business_relevance=0.5,
        detection_value=0.5,
        deployment_risk=0.2,
        confidence=confidence,
        reasoning="deterministic",
    )


def _analyze(calibration: ActiveCalibration | None = None):  # type: ignore[no-untyped-def]
    return _SERVICE.analyze(
        _SIGNALS, organization_id="org", request_id="req", calibration=calibration
    )


# ---- versions are always exposed -----------------------------------------------------------------


def test_result_always_exposes_engine_and_schema_versions() -> None:
    result = _analyze()
    assert result.schema_version
    assert result.engine_versions["context_engine"]
    assert result.engine_versions["placement_reasoning"]
    assert result.calibration.feature_schema_version == "features-v1"


def test_uncalibrated_result_states_the_deterministic_baseline() -> None:
    result = _analyze()
    assert result.calibration.applied is False
    assert result.calibration.model_version_id is None
    assert len(result.change_explanations) == len(result.placement_recommendations)
    for explanation in result.change_explanations:
        assert explanation.changed is False
        assert explanation.active_model_version is None
        assert "deterministic baseline" in explanation.explanation


def test_calibrated_result_exposes_the_active_model_version() -> None:
    version_id = uuid4()
    calibration = ActiveCalibration(
        model_version_id=version_id,
        weights=CalibrationWeights(zone_priors={"environment_file": 0.9}),
        organization_specific=True,
        cohort_samples={"environment_file": 12},
        cohort_intervals={"environment_file": (0.6, 0.95)},
    )
    result = _analyze(calibration)
    assert result.calibration.applied is True
    assert result.calibration.model_version_id == str(version_id)
    assert result.calibration.organization_specific is True
    for explanation in result.change_explanations:
        assert explanation.active_model_version == version_id


# ---- change explanation --------------------------------------------------------------------------


def test_prior_raises_confidence_and_explains_with_sample_evidence() -> None:
    calibration = ActiveCalibration(
        model_version_id=uuid4(),
        weights=CalibrationWeights(zone_priors={"payment": 1.0}),
        organization_specific=True,
        cohort_samples={"payment": 10},
        cohort_intervals={"payment": (0.55, 0.93)},
    )
    before = _rec("payment", 1, 0.5)
    after, explanations = apply_calibration((before,), calibration)
    assert after[0].confidence > before.confidence
    explanation = explanations[0]
    assert explanation.changed is True
    assert explanation.sample_count == 10
    assert explanation.confidence_interval == (0.55, 0.93)
    assert "10 attributable outcome" in explanation.explanation
    assert explanation.changed_factors == ("organization_zone_prior",)


def test_low_prior_reduces_confidence() -> None:
    calibration = ActiveCalibration(
        model_version_id=uuid4(),
        weights=CalibrationWeights(zone_priors={"payment": 0.0}),
        cohort_samples={"payment": 8},
    )
    after, explanations = apply_calibration((_rec("payment", 1, 0.8),), calibration)
    assert after[0].confidence < 0.8
    assert "reduced" in explanations[0].explanation


def test_zone_without_a_prior_explains_insufficient_evidence() -> None:
    calibration = ActiveCalibration(
        model_version_id=uuid4(), weights=CalibrationWeights(zone_priors={"payment": 0.9})
    )
    after, explanations = apply_calibration((_rec("documentation_file", 1, 0.6),), calibration)
    assert after[0].confidence == 0.6
    assert explanations[0].changed is False
    assert "below the promotion threshold" in explanations[0].explanation


def test_calibration_can_reorder_ranks_deterministically() -> None:
    calibration = ActiveCalibration(
        model_version_id=uuid4(),
        weights=CalibrationWeights(zone_priors={"payment": 1.0}),
        cohort_samples={"payment": 20},
    )
    recommendations = (_rec("documentation_file", 1, 0.70), _rec("payment", 2, 0.65))
    first, _ = apply_calibration(recommendations, calibration)
    second, _ = apply_calibration(recommendations, calibration)
    assert [r.zone for r in first] == [r.zone for r in second]  # deterministic
    assert first[0].zone == "payment"  # the calibrated prior promoted it
    assert first[0].rank == 1 and first[1].rank == 2


# ---- safety ----------------------------------------------------------------------------------


def test_calibration_never_alters_safety_relevant_fields() -> None:
    calibration = ActiveCalibration(
        model_version_id=uuid4(),
        weights=CalibrationWeights(zone_priors={"payment": 1.0}),
        cohort_samples={"payment": 25},
    )
    before = _rec("payment", 1, 0.5)
    after, _ = apply_calibration((before,), calibration)
    assert after[0].zone == before.zone
    assert after[0].proposed_path_or_pattern == before.proposed_path_or_pattern
    assert after[0].decoy_type == before.decoy_type
    assert after[0].deployment_risk == before.deployment_risk


def test_confidence_movement_is_bounded() -> None:
    """An extreme prior cannot move a deterministic confidence beyond the review bounds."""
    extreme = ActiveCalibration(
        model_version_id=uuid4(),
        weights=CalibrationWeights(zone_priors={"payment": 1.0}, confidence_scale=1.5),
        cohort_samples={"payment": 40},
    )
    after, _ = apply_calibration((_rec("payment", 1, 0.5),), extreme)
    assert after[0].confidence <= 0.5 * 1.25 + 1e-9


# ---- isolation -------------------------------------------------------------------------------


def test_another_organizations_calibration_does_not_leak_into_a_result() -> None:
    """A result carries only the calibration given to it; nothing else is consulted."""
    other = ActiveCalibration(
        model_version_id=uuid4(), weights=CalibrationWeights(zone_priors={"payment": 1.0})
    )
    uncalibrated = _analyze()
    calibrated = _analyze(other)
    assert uncalibrated.calibration.model_version_id is None
    assert calibrated.calibration.model_version_id == str(other.model_version_id)


def test_explanation_contains_no_other_tenant_identifiers() -> None:
    calibration = ActiveCalibration(
        model_version_id=uuid4(),
        weights=CalibrationWeights(zone_priors={"payment": 0.8}),
        organization_specific=True,
        cohort_samples={"payment": 9},
    )
    _, explanations = apply_calibration((_rec("payment", 1, 0.6),), calibration)
    text = explanations[0].explanation
    # Only aggregate evidence about "this organization" is described.
    assert "this organization" in text
    for token in ("org-", "organization_id=", "tenant"):
        assert token not in text


def test_endpoint_result_includes_calibration_block(make_client) -> None:  # type: ignore[no-untyped-def]
    from app.services.api_keys import ApiKeyService

    with make_client(demo_enabled=False, auth_enabled=True, app_env="development") as client:
        org = str(uuid4())
        session = client.app_session()
        _, key = ApiKeyService(session).create(UUID(org), "analyst", "analyst")
        session.commit()
        session.close()
        response = client.post(
            "/api/v1/analysis/preview",
            json={"signals": {"services": [{"name": "payment-service"}]}},
            headers={"X-DeceptiForge-API-Key": key, "X-DeceptiForge-Org-Id": org},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["calibration"]["applied"] is False  # learning disabled by default
        assert body["calibration"]["feature_schema_version"] == "features-v1"
        assert len(body["change_explanations"]) == len(body["placement_recommendations"])
