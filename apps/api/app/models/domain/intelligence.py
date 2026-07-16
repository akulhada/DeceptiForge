"""Stable, transport-neutral contracts for repository and organization intelligence."""
from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from app.models.domain.base import DomainModel
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
