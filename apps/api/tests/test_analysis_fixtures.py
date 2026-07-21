# Purpose: verify deterministic inference for every shared scenario fixture against its expected
#   high-level result in the manifest. Assertions target stable identifiers, categories, score
#   ranges, and warning codes — never brittle full-prose strings.
from __future__ import annotations

import pytest

from app.models.domain.analysis_signals import RepositorySignals
from app.services.analysis_lab import AnalysisPreviewService
from app.services.analysis_lab.scenarios import Scenario, load_scenarios

_SERVICE = AnalysisPreviewService()
_SCENARIOS = load_scenarios()
_DOMAIN_LABEL = {
    "fintech": "Financial / payments platform",
    "healthcare": "Healthcare application",
    "ecommerce": "E-commerce platform",
    "saas_crm": "SaaS customer-management system",
    "ml_data": "Data / ML platform",
    "unknown": "unknown",
}


def test_all_ten_scenarios_present() -> None:
    assert len(_SCENARIOS) == 10


def _run(scenario: Scenario):  # type: ignore[no-untyped-def]
    signals = RepositorySignals.model_validate(scenario.signals)
    return _SERVICE.analyze(
        signals, organization_id="o", request_id="r", scenario_id=scenario.scenario_id
    )


@pytest.mark.parametrize("scenario", _SCENARIOS, ids=[s.scenario_id for s in _SCENARIOS])
def test_scenario_matches_expectations(scenario: Scenario) -> None:
    result = _run(scenario)
    exp = scenario.expected

    if "business_domain" in exp:
        expected_label = _DOMAIN_LABEL[exp["business_domain"]]
        assert result.context_profile.probable_business_domain.value == expected_label

    if "service_architecture" in exp:
        assert result.context_profile.service_architecture.value == exp["service_architecture"]

    if "repository_type" in exp:
        assert result.context_profile.probable_repository_type.value in set(exp["repository_type"])

    if "data_sensitivity" in exp:
        assert result.context_profile.data_sensitivity.value == exp["data_sensitivity"]

    zone_categories = {z.category for z in result.sensitive_zones}
    for category in exp.get("sensitive_zone_categories", []):
        assert category in zone_categories, f"{scenario.scenario_id}: missing zone {category}"

    if "top_zone_category" in exp:
        assert result.sensitive_zones[0].category == exp["top_zone_category"]

    codes = {w.code for w in result.warnings}
    for code in exp.get("warning_codes_present", []):
        assert code in codes, f"{scenario.scenario_id}: expected warning {code}"
    for code in exp.get("warning_codes_absent", []):
        assert code not in codes, f"{scenario.scenario_id}: unexpected warning {code}"

    if "overall_confidence_min" in exp:
        assert result.confidence.overall >= exp["overall_confidence_min"]
    if "overall_confidence_max" in exp:
        assert result.confidence.overall <= exp["overall_confidence_max"]
    if "conflict_min" in exp:
        assert result.confidence.conflict >= exp["conflict_min"]
    if "ai_exposure_min" in exp:
        assert result.context_profile.ai_system_exposure.confidence >= exp["ai_exposure_min"]


def test_determinism_same_input_same_output() -> None:
    scenario = next(s for s in _SCENARIOS if s.scenario_id == "fintech-payments")
    a = _run(scenario).model_dump(exclude={"generated_at", "stage_timings_ms"})
    b = _run(scenario).model_dump(exclude={"generated_at", "stage_timings_ms"})
    assert a == b


def test_sparse_does_not_fabricate_domain() -> None:
    scenario = next(s for s in _SCENARIOS if s.scenario_id == "sparse")
    result = _run(scenario)
    assert result.context_profile.probable_business_domain.value == "unknown"
    assert result.context_profile.probable_business_domain.confidence == 0.0


def test_repeated_evidence_does_not_inflate_zone_scores() -> None:
    base = {"secret_locations": [{"path": "a/.env.example", "category": "secret"}]}
    repeated = {
        "secret_locations": [
            {"path": f"a/{i}.env.example", "category": "secret"} for i in range(20)
        ]
    }
    s1 = _SERVICE.analyze(
        RepositorySignals.model_validate(base), organization_id="o", request_id="r"
    )
    s2 = _SERVICE.analyze(
        RepositorySignals.model_validate(repeated), organization_id="o", request_id="r"
    )
    z1 = next(z for z in s1.sensitive_zones if z.category == "secrets_and_credentials")
    z2 = next(z for z in s2.sensitive_zones if z.category == "secrets_and_credentials")
    # Distinct-keyword coverage drives the score, so 20x repetition must not raise risk.
    assert z2.risk_score == z1.risk_score


def test_conflict_lowers_domain_confidence() -> None:
    conflicting = next(s for s in _SCENARIOS if s.scenario_id == "conflicting")
    clean = next(s for s in _SCENARIOS if s.scenario_id == "fintech-payments")
    assert _run(conflicting).confidence.conflict > 0
    assert _run(clean).confidence.conflict == 0
