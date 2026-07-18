# Purpose: model organization, repository, and repository-profile aggregates. Responsibilities:
# represent durable ownership and observed repository context without scan behavior. Future
# modules: add approved profile revisions and repository integrations.
from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field

from app.models.domain.base import (
    DomainModel,
    OrganizationId,
    RepositoryId,
    RepositoryProfileId,
    RepositoryStatistics,
)


class RepositoryProvider(StrEnum):
    """Supported source-control provider identities."""

    GITHUB = "github"
    GITLAB = "gitlab"
    BITBUCKET = "bitbucket"
    AZURE_DEVOPS = "azure_devops"
    SELF_HOSTED_GIT = "self_hosted_git"
    OTHER = "other"


class CloudProvider(StrEnum):
    """Cloud providers detected in repository context."""

    AWS = "aws"
    AZURE = "azure"
    GCP = "gcp"
    CLOUDFLARE = "cloudflare"
    DIGITALOCEAN = "digitalocean"
    OTHER = "other"
    UNKNOWN = "unknown"


class EnvironmentVariableStyle(StrEnum):
    """Naming styles observed in environment configuration."""

    UPPER_SNAKE_CASE = "upper_snake_case"
    LOWER_SNAKE_CASE = "lower_snake_case"
    KEBAB_CASE = "kebab_case"
    MIXED = "mixed"
    UNKNOWN = "unknown"


class RiskLevel(StrEnum):
    """Stable severity vocabulary shared by risk-bearing models."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class TechnologyEvidence(DomainModel):
    """A technology detection with provenance.

    Purpose: preserve why a scanner inferred a language, framework, service, or tool.
    Fields: canonical name, confidence, and bounded evidence references.
    Relationships: embedded by RepositoryProfile and never owns a repository.
    Future extensibility: add detector version and normalized taxonomy IDs.
    """

    name: str = Field(min_length=1, max_length=128)
    confidence: float = Field(ge=0, le=1)
    evidence: tuple[str, ...] = Field(default=(), max_length=20)


class RiskArea(DomainModel):
    """A repository-context risk observation.

    Purpose: retain risk signals without encoding remediation policy.
    Fields: category, severity, confidence, and explanation.
    Relationships: embedded in RepositoryProfile and informs future placement decisions.
    Future extensibility: add stable taxonomy codes and external evidence IDs.
    """

    category: str = Field(min_length=1, max_length=128)
    severity: RiskLevel
    confidence: float = Field(ge=0, le=1)
    explanation: str = Field(min_length=1, max_length=2000)


class NamingPattern(DomainModel):
    """A naming convention observed in a repository.

    Purpose: capture context needed for believable generated assets.
    Fields: scope, pattern expression, sample count, and confidence.
    Relationships: embedded in RepositoryProfile and consumed by future decoy generation.
    Future extensibility: add language-specific parsers while preserving the normalized expression.
    """

    scope: str = Field(min_length=1, max_length=128)
    expression: str = Field(min_length=1, max_length=512)
    sample_count: int = Field(ge=1)
    confidence: float = Field(ge=0, le=1)


class Organization(DomainModel):
    """The tenant boundary that owns repositories and security outcomes.

    Purpose: establish durable ownership and isolation.
    Fields: typed ID, display name, slug, creation timestamp, and schema revision.
    Relationships: one organization owns many Repository aggregates.
    Future extensibility: add tenancy policy references without embedding user membership.
    """

    id: OrganizationId
    name: str = Field(min_length=1, max_length=256)
    slug: str = Field(pattern=r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
    created_at: datetime
    schema_version: int = Field(default=1, ge=1)


class Repository(DomainModel):
    """A source-control repository owned by an organization.

    Purpose: identify a scanned codebase without storing source content.
    Fields: typed IDs, provider identity, canonical URL, default branch, and timestamps.
    Relationships: belongs to Organization and has many immutable RepositoryProfile snapshots.
    Future extensibility: add provider installation references and archival state explicitly.
    """

    id: RepositoryId
    organization_id: OrganizationId
    provider: RepositoryProvider
    provider_repository_id: str = Field(min_length=1, max_length=256)
    canonical_url: str = Field(min_length=1, max_length=2048)
    default_branch: str = Field(min_length=1, max_length=255)
    created_at: datetime
    updated_at: datetime
    schema_version: int = Field(default=1, ge=1)


class RepositoryProfile(DomainModel):
    """An immutable observed-context snapshot for one repository revision.

    Purpose: hold scanner-derived context used by generation, placement, and coverage.
    Fields: detected technologies, cloud and environment style, statistics, risks, and naming
    patterns.
    Relationships: belongs to Repository; all detection records are embedded to preserve snapshot
    integrity.
    Future extensibility: add new evidence categories with separate fields, never overload existing
    ones.
    """

    id: RepositoryProfileId
    repository_id: RepositoryId
    repository_revision: str = Field(min_length=1, max_length=128)
    generated_at: datetime
    languages: tuple[TechnologyEvidence, ...] = ()
    frameworks: tuple[TechnologyEvidence, ...] = ()
    services: tuple[TechnologyEvidence, ...] = ()
    infrastructure: tuple[TechnologyEvidence, ...] = ()
    cloud_provider: CloudProvider = CloudProvider.UNKNOWN
    environment_variable_style: EnvironmentVariableStyle = EnvironmentVariableStyle.UNKNOWN
    statistics: RepositoryStatistics
    detected_technologies: tuple[TechnologyEvidence, ...] = ()
    risk_areas: tuple[RiskArea, ...] = ()
    naming_patterns: tuple[NamingPattern, ...] = ()
    schema_version: int = Field(default=1, ge=1)
