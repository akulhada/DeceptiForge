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
from app.services.context_engine.engine import ContextEngine


def evidence(name: str) -> TechnologyEvidence:
    return TechnologyEvidence(name=name, confidence=0.9, evidence=(name,))


def test_assembles_mixed_stack_context_and_ranks_sensitive_zones() -> None:
    context = ContextEngine().build(
        RepositoryIntelligenceProfile(
            repository_name="payments",
            root_path="/repos/payments",
            is_git_repository=True,
            file_count=12,
            frameworks=(evidence("FastAPI"),),
            package_managers=(evidence("Poetry"),),
            services=(evidence("invoice-worker"),),
            databases=(evidence("PostgreSQL"),),
            cloud_providers=(evidence("AWS"),),
            mcp_configurations=(evidence("MCP"),),
            documentation=(evidence("runbook"),),
            infrastructure=InfrastructureHints(
                docker_files=("Dockerfile",), terraform_files=("infra/main.tf",)
            ),
            secret_locations=(SecretLocation(path=".env.example", patterns=("JWT_SECRET",)),),
            naming_profile=NamingProfile(
                naming_style=(
                    NamingConvention(
                        category=NamingCategory.ENVIRONMENT_VARIABLE,
                        style=NamingStyle.SCREAMING_SNAKE,
                        separator=Separator.UNDERSCORE,
                        support=3,
                        confidence=1.0,
                    ),
                ),
                vocabulary=(),
                separators=(),
                confidence=0.8,
            ),
            confidence_metadata=(
                AnalyzerConfidence(analyzer="language", confidence=0.9, evidence_count=2),
            ),
        )
    )

    assert context.organization_archetype.value == "cloud_native_platform"
    assert context.likely_decoy_placement_zones[0].name == "configuration"
    assert "database_record" in context.likely_sensitive_asset_types
    assert context.environment_naming_conventions == (
        "environment_variable:screaming_snake:underscore",
    )
    assert context.ai_exposure_risk > 0


def test_empty_profile_has_safe_unknown_fallback() -> None:
    context = ContextEngine().build(
        RepositoryIntelligenceProfile(
            repository_name="empty", root_path="/empty", is_git_repository=True, file_count=0
        )
    )

    assert context.organization_archetype.value == "unknown"
    assert context.confidence == 0
    assert context.likely_decoy_placement_zones == ()
