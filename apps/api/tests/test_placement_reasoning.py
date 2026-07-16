from app.models.domain.intelligence import (
    AnalyzerConfidence,
    InfrastructureHints,
    NamingCategory,
    NamingConvention,
    NamingProfile,
    NamingStyle,
    RepositoryIntelligenceProfile,
    SecretLocation,
    Separator,
)
from app.models.domain.organization import TechnologyEvidence
from app.services.context_engine import ContextEngine
from app.services.placement_reasoning import PlacementReasoningEngine


def evidence(name: str, path: str) -> TechnologyEvidence:
    return TechnologyEvidence(name=name, confidence=0.9, evidence=(path,))


def mixed_profile() -> RepositoryIntelligenceProfile:
    return RepositoryIntelligenceProfile(
        repository_name="payments",
        root_path="/repos/payments",
        is_git_repository=True,
        file_count=30,
        frameworks=(evidence("FastAPI", "api/main.py"),),
        services=(evidence("payment-service", "services/payment-service.py"),),
        databases=(evidence("PostgreSQL", "app/database.py"),),
        cicd=(evidence("GitHub Actions", ".github/workflows/test.yml"),),
        documentation=(evidence("Markdown", "docs/architecture.md"),),
        mcp_configurations=(evidence("MCP", ".cursor/mcp.json"),),
        infrastructure=InfrastructureHints(docker_files=("Dockerfile",)),
        folder_structure=("reports", "scripts"),
        secret_locations=(
            SecretLocation(path=".env", patterns=()),
            SecretLocation(path=".env.example", patterns=()),
        ),
        naming_profile=NamingProfile(
            naming_style=(
                NamingConvention(
                    category=NamingCategory.ENVIRONMENT_VARIABLE,
                    style=NamingStyle.SCREAMING_SNAKE,
                    separator=Separator.UNDERSCORE,
                    support=2,
                    confidence=1.0,
                ),
            ),
            confidence=0.8,
        ),
        confidence_metadata=(
            AnalyzerConfidence(analyzer="repository", confidence=0.9, evidence_count=8),
        ),
    )


def test_ranks_safe_locations_and_explains_them() -> None:
    profile = mixed_profile()
    plan = PlacementReasoningEngine().plan(profile, ContextEngine().build(profile))

    assert plan.recommendations
    assert plan.recommendations == tuple(
        sorted(
            plan.recommendations,
            key=lambda item: (-item.placement_priority, -item.confidence, item.target_location),
        )
    )
    example = next(item for item in plan.recommendations if item.target_location == ".env.example")
    assert example.expected_detection_quality > 0.75
    assert any("Safety is" in line for line in example.reasoning)


def test_rejects_unsafe_environment_and_database_locations() -> None:
    profile = mixed_profile()
    plan = PlacementReasoningEngine().plan(profile, ContextEngine().build(profile))

    rejected = {item.target_location: item.rejection_reasons for item in plan.rejected_candidates}
    assert any("production environment" in reason for reason in rejected[".env"])
    assert any(location.startswith("database://") for location in rejected)


def test_empty_profile_returns_empty_plan() -> None:
    profile = RepositoryIntelligenceProfile(
        repository_name="empty", root_path="/repos/empty", is_git_repository=True, file_count=0
    )

    plan = PlacementReasoningEngine().plan(profile, ContextEngine().build(profile))

    assert plan.recommendations == ()
    assert plan.rejected_candidates == ()
