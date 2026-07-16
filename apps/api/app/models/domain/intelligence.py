"""Stable, transport-neutral contracts for repository and organization intelligence."""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from app.models.domain.base import DomainModel
from app.models.domain.decoy import DecoyKind
from app.models.domain.organization import RiskLevel, TechnologyEvidence


class NamingCategory(StrEnum):
    ENVIRONMENT_VARIABLE = "environment_variable"
    SERVICE = "service"
    DATABASE = "database"
    FILE = "file"
    FOLDER = "folder"
    API = "api"
    RESOURCE = "resource"


class NamingStyle(StrEnum):
    SCREAMING_SNAKE = "screaming_snake"
    SNAKE = "snake"
    KEBAB = "kebab"
    DOT = "dot"
    CAMEL = "camel"
    PASCAL = "pascal"
    FLAT_LOWER = "flat_lower"
    FLAT_UPPER = "flat_upper"


class Separator(StrEnum):
    UNDERSCORE = "underscore"
    HYPHEN = "hyphen"
    DOT = "dot"
    SLASH = "slash"
    NONE = "none"


class NamingConvention(DomainModel):
    category: NamingCategory
    style: NamingStyle
    separator: Separator
    support: int = Field(ge=1)
    confidence: float = Field(ge=0, le=1)
    samples: tuple[str, ...] = Field(default=(), max_length=5)


class VocabularyTerm(DomainModel):
    value: str = Field(min_length=1, max_length=128)
    support: int = Field(ge=1)


class SeparatorUsage(DomainModel):
    separator: Separator
    support: int = Field(ge=1)
    confidence: float = Field(ge=0, le=1)


class NamingProfile(DomainModel):
    naming_style: tuple[NamingConvention, ...] = ()
    common_prefixes: tuple[str, ...] = ()
    common_suffixes: tuple[str, ...] = ()
    vocabulary: tuple[VocabularyTerm, ...] = ()
    separators: tuple[SeparatorUsage, ...] = ()
    confidence: float = Field(ge=0, le=1)


class InfrastructureHints(DomainModel):
    docker_files: tuple[str, ...] = ()
    kubernetes_files: tuple[str, ...] = ()
    terraform_files: tuple[str, ...] = ()


class SecretLocation(DomainModel):
    path: str = Field(min_length=1, max_length=2048)
    patterns: tuple[str, ...] = ()


class IntelligenceRiskArea(DomainModel):
    category: str = Field(min_length=1, max_length=128)
    severity: RiskLevel
    description: str = Field(min_length=1, max_length=2000)
    paths: tuple[str, ...] = ()


class AnalyzerConfidence(DomainModel):
    analyzer: str = Field(min_length=1, max_length=128)
    confidence: float = Field(ge=0, le=1)
    evidence_count: int = Field(ge=0)


class RepositoryIntelligenceProfile(DomainModel):
    repository_name: str = Field(min_length=1, max_length=256)
    root_path: str = Field(min_length=1, max_length=2048)
    is_git_repository: bool
    file_count: int = Field(ge=0)
    folder_structure: tuple[str, ...] = ()
    languages: tuple[TechnologyEvidence, ...] = ()
    frameworks: tuple[TechnologyEvidence, ...] = ()
    package_managers: tuple[TechnologyEvidence, ...] = ()
    services: tuple[TechnologyEvidence, ...] = ()
    technologies: tuple[TechnologyEvidence, ...] = ()
    databases: tuple[TechnologyEvidence, ...] = ()
    cloud_providers: tuple[TechnologyEvidence, ...] = ()
    cicd: tuple[TechnologyEvidence, ...] = ()
    documentation: tuple[TechnologyEvidence, ...] = ()
    mcp_configurations: tuple[TechnologyEvidence, ...] = ()
    infrastructure: InfrastructureHints = Field(default_factory=InfrastructureHints)
    naming_profile: NamingProfile | None = None
    secret_locations: tuple[SecretLocation, ...] = ()
    risk_areas: tuple[IntelligenceRiskArea, ...] = ()
    confidence_metadata: tuple[AnalyzerConfidence, ...] = ()
    truncated: bool = False


class OrganizationArchetype(StrEnum):
    APPLICATION_SERVICE = "application_service"
    CLOUD_NATIVE_PLATFORM = "cloud_native_platform"
    DATA_SERVICE = "data_service"
    DEVELOPER_TOOLING = "developer_tooling"
    UNKNOWN = "unknown"


class StackMaturity(StrEnum):
    EXPERIMENTAL = "experimental"
    ESTABLISHED = "established"
    MATURE = "mature"
    UNKNOWN = "unknown"


class DocumentationCulture(StrEnum):
    NONE = "none"
    LIGHT = "light"
    OPERATIONAL = "operational"
    STRUCTURED = "structured"


class ContextArea(DomainModel):
    name: str = Field(min_length=1, max_length=128)
    priority: float = Field(ge=0, le=1)
    rationale: str = Field(min_length=1, max_length=1000)
    evidence: tuple[str, ...] = ()


class ContextConfidence(DomainModel):
    dimension: str = Field(min_length=1, max_length=128)
    confidence: float = Field(ge=0, le=1)
    evidence_count: int = Field(ge=0)


class ContextReasoning(DomainModel):
    dimension: str = Field(min_length=1, max_length=128)
    conclusion: str = Field(min_length=1, max_length=1000)
    evidence: tuple[str, ...] = ()


class OrganizationContextProfile(DomainModel):
    repository_name: str
    organization_archetype: OrganizationArchetype
    stack_maturity: StackMaturity
    primary_technical_vocabulary: tuple[VocabularyTerm, ...] = ()
    environment_naming_conventions: tuple[str, ...] = ()
    likely_sensitive_asset_types: tuple[str, ...] = ()
    likely_decoy_placement_zones: tuple[ContextArea, ...] = ()
    high_value_systems: tuple[str, ...] = ()
    likely_workflow_surfaces: tuple[str, ...] = ()
    ai_exposure_risk: float = Field(ge=0, le=1)
    database_sensitivity_confidence: float = Field(ge=0, le=1)
    documentation_culture: DocumentationCulture
    operational_complexity: str
    security_posture_hints: tuple[str, ...] = ()
    technologies: tuple[TechnologyEvidence, ...] = ()
    naming_profile: NamingProfile | None = None
    confidence_metadata: tuple[ContextConfidence, ...] = ()
    reasoning: tuple[ContextReasoning, ...] = ()
    confidence: float = Field(ge=0, le=1)


class PlacementTargetType(StrEnum):
    """Repository and knowledge surfaces evaluated before any asset is generated."""

    AGENT_ACCESSIBLE_FOLDER = "agent_accessible_folder"
    ARCHITECTURE_DOCUMENT = "architecture_document"
    BROWSER_AI_WORKFLOW = "browser_ai_workflow"
    CI_CD_FILE = "ci_cd_file"
    CONFIG_FILE = "config_file"
    DATABASE_ROW = "database_row"
    DOCUMENTATION_FILE = "documentation_file"
    ENVIRONMENT_FILE = "environment_file"
    EXAMPLE_ENVIRONMENT_FILE = "example_environment_file"
    EXPORTABLE_REPORT = "exportable_report"
    INTERNAL_WIKI_PAGE = "internal_wiki_page"
    LEGACY_SCRIPT = "legacy_script"
    MCP_CONFIG = "mcp_config"
    RAG_DOCUMENT = "rag_document"
    SPREADSHEET_ROW = "spreadsheet_row"


class PlacementSignals(DomainModel):
    attacker_visibility: float = Field(ge=0, le=1)
    ai_agent_access: float = Field(ge=0, le=1)
    insider_access: float = Field(ge=0, le=1)
    exportability: float = Field(ge=0, le=1)
    accidental_exposure: float = Field(ge=0, le=1)
    plausibility: float = Field(ge=0, le=1)
    safety: float = Field(ge=0, le=1)
    context_alignment: float = Field(ge=0, le=1)
    false_positive_risk: float = Field(ge=0, le=1)


class PlacementCandidate(DomainModel):
    target_type: PlacementTargetType
    target_location: str = Field(min_length=1, max_length=2048)
    future_asset_type: DecoyKind
    evidence: tuple[str, ...] = ()
    signals: PlacementSignals
    requires_nonproduction_scope: bool = False


class PlacementScore(DomainModel):
    priority: float = Field(ge=0, le=1)
    confidence: float = Field(ge=0, le=1)
    detection_quality: float = Field(ge=0, le=1)
    risk: float = Field(ge=0, le=1)
    expected_visibility: float = Field(ge=0, le=1)
    false_positive_risk: float = Field(ge=0, le=1)


class PlacementRecommendation(DomainModel):
    target_type: PlacementTargetType
    target_location: str = Field(min_length=1, max_length=2048)
    placement_priority: float = Field(ge=0, le=1)
    confidence: float = Field(ge=0, le=1)
    reasoning: tuple[str, ...] = Field(min_length=1)
    expected_detection_quality: float = Field(ge=0, le=1)
    risk_score: float = Field(ge=0, le=1)
    expected_attacker_agent_visibility: float = Field(ge=0, le=1)
    expected_false_positive_risk: float = Field(ge=0, le=1)
    future_asset_type_recommendation: DecoyKind
    evidence: tuple[str, ...] = ()


class RejectedPlacementCandidate(DomainModel):
    target_type: PlacementTargetType
    target_location: str = Field(min_length=1, max_length=2048)
    rejection_reasons: tuple[str, ...] = Field(min_length=1)


class PlacementPlan(DomainModel):
    repository_name: str = Field(min_length=1, max_length=256)
    context: OrganizationContextProfile
    recommendations: tuple[PlacementRecommendation, ...] = ()
    rejected_candidates: tuple[RejectedPlacementCandidate, ...] = ()
