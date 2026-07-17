from app.models.domain.decoy import DecoyKind, GeneratedDocument, GeneratedSecret
from app.models.domain.intelligence import (
    DocumentationCulture,
    NamingCategory,
    NamingConvention,
    NamingProfile,
    NamingStyle,
    OrganizationArchetype,
    OrganizationContextProfile,
    PlacementPlan,
    PlacementRecommendation,
    PlacementTargetType,
    RepositoryIntelligenceProfile,
    Separator,
    StackMaturity,
)
from app.services.believability import BelievabilitySafetyConfig, BelievabilitySafetyEngine
from app.services.believability.scoring import ScoringWeights
from app.services.decoy_generation import DecoyGenerationPlanner


def context(with_naming: bool = True) -> OrganizationContextProfile:
    return OrganizationContextProfile(
        repository_name="payments",
        organization_archetype=OrganizationArchetype.APPLICATION_SERVICE,
        stack_maturity=StackMaturity.ESTABLISHED,
        ai_exposure_risk=0.1,
        database_sensitivity_confidence=0.8,
        documentation_culture=DocumentationCulture.LIGHT,
        operational_complexity="moderate",
        naming_profile=(
            NamingProfile(
                naming_style=(
                    NamingConvention(
                        category=NamingCategory.ENVIRONMENT_VARIABLE,
                        style=NamingStyle.SCREAMING_SNAKE,
                        separator=Separator.UNDERSCORE,
                        support=2,
                        confidence=1,
                        samples=("PAYMENT_SERVICE_KEY",),
                    ),
                ),
                confidence=1,
            )
            if with_naming
            else None
        ),
        environment_naming_conventions=("environment_variable:screaming_snake:underscore",),
        confidence=0.9,
    )


def recommendation(kind: DecoyKind, target: PlacementTargetType) -> PlacementRecommendation:
    return PlacementRecommendation(
        target_type=target,
        target_location=".env.example" if kind is DecoyKind.SECRET else "docs/runbook.md",
        placement_priority=0.9,
        confidence=0.9,
        reasoning=("accepted",),
        expected_detection_quality=0.8,
        risk_score=0.1,
        expected_attacker_agent_visibility=0.8,
        expected_false_positive_risk=0.1,
        future_asset_type_recommendation=kind,
    )


def generated(kind: DecoyKind = DecoyKind.SECRET):
    placement = recommendation(
        kind,
        (
            PlacementTargetType.EXAMPLE_ENVIRONMENT_FILE
            if kind is DecoyKind.SECRET
            else PlacementTargetType.DOCUMENTATION_FILE
        ),
    )
    asset = (
        DecoyGenerationPlanner()
        .generate(
            RepositoryIntelligenceProfile(
                repository_name="payments", root_path="/repo", is_git_repository=True, file_count=1
            ),
            context(),
            PlacementPlan(
                repository_name="payments", context=context(), recommendations=(placement,)
            ),
        )
        .assets[0]
    )
    return asset, placement


def test_high_quality_asset_is_accepted_deterministically() -> None:
    asset, placement = generated()
    repository = RepositoryIntelligenceProfile(
        repository_name="payments", root_path="/repo", is_git_repository=True, file_count=1
    )

    first = BelievabilitySafetyEngine().evaluate(asset, context(), repository, placement)
    second = BelievabilitySafetyEngine().evaluate(asset, context(), repository, placement)

    assert first == second
    assert first.decision.value == "accept"
    assert first.overall_believability_score >= 80
    assert first.breakdown.traceability_quality == 100
    assert first.explainability_notes


def test_obvious_or_unsafe_secret_is_rejected() -> None:
    asset, placement = generated()
    assert isinstance(asset.payload, GeneratedSecret)
    asset = asset.model_copy(
        update={"payload": asset.payload.model_copy(update={"fake_value": "CANARY_TOKEN"})}
    )
    repository = RepositoryIntelligenceProfile(
        repository_name="payments", root_path="/repo", is_git_repository=True, file_count=1
    )

    report = BelievabilitySafetyEngine().evaluate(asset, context(), repository, placement)

    assert report.decision.value == "reject"
    assert report.breakdown.obvious_trap_risk == 100
    assert report.failed_checks


def test_collision_naming_and_placement_mismatches_are_explained() -> None:
    asset, placement = generated()
    assert isinstance(asset.payload, GeneratedSecret)
    mismatched = asset.model_copy(
        update={"payload": asset.payload.model_copy(update={"key_name": "payment-token"})}
    )
    repository = RepositoryIntelligenceProfile(
        repository_name="payments", root_path="/repo", is_git_repository=True, file_count=1
    )
    collision = BelievabilitySafetyEngine().evaluate(
        asset,
        context(),
        repository,
        placement,
        BelievabilitySafetyConfig(reserved_names=("PLATFORM_SERVICE_TOKEN",)),
    )
    incompatible = BelievabilitySafetyEngine().evaluate(
        mismatched,
        context(),
        repository,
        recommendation(DecoyKind.SECRET, PlacementTargetType.DOCUMENTATION_FILE),
    )

    assert collision.decision.value == "reject"
    assert collision.breakdown.production_collision_risk == 100
    assert incompatible.breakdown.naming_realism < 90
    assert incompatible.breakdown.placement_compatibility == 0
    assert incompatible.recommended_fixes


def test_missing_traceability_and_configurable_weights_change_outcome() -> None:
    asset, placement = generated(DecoyKind.DOCUMENT)
    assert isinstance(asset.payload, GeneratedDocument)
    asset = asset.model_copy(
        update={"payload": asset.payload.model_copy(update={"trace_identifier": "OTHER"})}
    )
    repository = RepositoryIntelligenceProfile(
        repository_name="payments", root_path="/repo", is_git_repository=True, file_count=0
    )

    report = BelievabilitySafetyEngine().evaluate(asset, context(False), repository, placement)
    reweighted = BelievabilitySafetyEngine().evaluate(
        asset,
        context(False),
        repository,
        placement,
        BelievabilitySafetyConfig(weights=ScoringWeights(traceability=60, naming=1)),
    )

    assert report.decision.value == "reject"
    assert "traceability" in report.failed_checks[0]
    assert reweighted.overall_believability_score != report.overall_believability_score
    assert "Sparse context" in report.warnings[0]
