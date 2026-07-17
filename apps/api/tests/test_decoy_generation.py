from app.models.domain.decoy import (
    DecoyKind,
    GeneratedDatabaseRecord,
    GeneratedDocument,
    GeneratedSecret,
)
from app.models.domain.intelligence import (
    DocumentationCulture,
    OrganizationArchetype,
    OrganizationContextProfile,
    PlacementPlan,
    PlacementRecommendation,
    PlacementTargetType,
    RepositoryIntelligenceProfile,
    StackMaturity,
)
from app.services.decoy_generation import DecoyGenerationConfig, DecoyGenerationPlanner


def context() -> OrganizationContextProfile:
    return OrganizationContextProfile(
        repository_name="payments",
        organization_archetype=OrganizationArchetype.APPLICATION_SERVICE,
        stack_maturity=StackMaturity.ESTABLISHED,
        ai_exposure_risk=0.2,
        database_sensitivity_confidence=0.8,
        documentation_culture=DocumentationCulture.LIGHT,
        operational_complexity="moderate",
        confidence=0.9,
    )


def recommendation(target_type: PlacementTargetType, kind: DecoyKind) -> PlacementRecommendation:
    return PlacementRecommendation(
        target_type=target_type,
        target_location={
            PlacementTargetType.EXAMPLE_ENVIRONMENT_FILE: ".env.example",
            PlacementTargetType.DOCUMENTATION_FILE: "docs/runbook.md",
            PlacementTargetType.DATABASE_ROW: "database://postgresql/synthetic-row",
        }[target_type],
        placement_priority=0.9,
        confidence=0.9,
        reasoning=("accepted",),
        expected_detection_quality=0.8,
        risk_score=0.1,
        expected_attacker_agent_visibility=0.8,
        expected_false_positive_risk=0.1,
        future_asset_type_recommendation=kind,
    )


def plan(*recommendations: PlacementRecommendation) -> PlacementPlan:
    return PlacementPlan(
        repository_name="payments", context=context(), recommendations=recommendations
    )


def repository() -> RepositoryIntelligenceProfile:
    return RepositoryIntelligenceProfile(
        repository_name="payments",
        root_path="/repos/payments",
        is_git_repository=True,
        file_count=2,
    )


def test_generates_deterministic_secret_document_and_database_assets() -> None:
    placements = plan(
        recommendation(PlacementTargetType.EXAMPLE_ENVIRONMENT_FILE, DecoyKind.SECRET),
        recommendation(PlacementTargetType.DOCUMENTATION_FILE, DecoyKind.DOCUMENT),
        recommendation(PlacementTargetType.DATABASE_ROW, DecoyKind.DATABASE_RECORD),
    )

    first = DecoyGenerationPlanner().generate(repository(), context(), placements)
    second = DecoyGenerationPlanner().generate(repository(), context(), placements)

    assert first == second
    assert len(first.assets) == 3
    assert isinstance(first.assets[0].payload, GeneratedSecret)
    assert any(isinstance(asset.payload, GeneratedDocument) for asset in first.assets)
    assert any(isinstance(asset.payload, GeneratedDatabaseRecord) for asset in first.assets)
    assert all(asset.validation.valid for asset in first.assets)
    assert all(asset.safety_metadata.authentication_capability == "none" for asset in first.assets)
    assert all(asset.model_dump(mode="json") for asset in first.assets)


def test_ignores_rejected_placements_and_unsupported_or_unsafe_recommendations() -> None:
    unsafe = recommendation(
        PlacementTargetType.EXAMPLE_ENVIRONMENT_FILE, DecoyKind.SECRET
    ).model_copy(update={"confidence": 0.2})
    unsupported = recommendation(PlacementTargetType.DOCUMENTATION_FILE, DecoyKind.SECRET)
    placements = plan(unsafe, unsupported)
    placements = placements.model_copy(
        update={
            "rejected_candidates": (),
        }
    )

    result = DecoyGenerationPlanner().generate(repository(), context(), placements)

    assert result.assets == ()
    assert len(result.rejected_candidates) == 2


def test_collision_validation_rejects_reserved_generated_key_name() -> None:
    placements = plan(
        recommendation(PlacementTargetType.EXAMPLE_ENVIRONMENT_FILE, DecoyKind.SECRET)
    )

    result = DecoyGenerationPlanner().generate(
        repository(),
        context(),
        placements,
        DecoyGenerationConfig(reserved_names=("PLATFORM_SERVICE_TOKEN",)),
    )

    assert result.assets == ()
    assert "collides" in result.rejected_candidates[0].reasons[0]
