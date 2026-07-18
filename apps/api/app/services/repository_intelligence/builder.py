# Purpose: fold independent analyzer contributions into one repository intelligence profile.
# Responsibilities: merge additive fields deterministically and derive profile-level values from
#   the crawl evidence. Dependencies: domain contracts, evidence, and analyzer contributions.
from __future__ import annotations

from pathlib import PurePath
from typing import Any

from app.models.domain.intelligence import InfrastructureHints, RepositoryIntelligenceProfile
from app.services.repository_intelligence.analyzers import AnalyzerContribution
from app.services.repository_intelligence.evidence import RepositoryEvidence

_MERGED_FIELDS: tuple[str, ...] = (
    "languages",
    "frameworks",
    "package_managers",
    "services",
    "databases",
    "cloud_providers",
    "cicd",
    "documentation",
    "mcp_configurations",
    "secret_locations",
    "risk_areas",
)


class ProfileBuilder:
    """Assembles the final profile from evidence and analyzer contributions.

    Merge rules: additive tuple fields are concatenated in analyzer order; the singular
    ``infrastructure`` and ``naming_profile`` take the first analyzer that provides them.
    Complexity: O(sum of contribution sizes). The builder performs no I/O.
    """

    def build(
        self,
        evidence: RepositoryEvidence,
        contributions: tuple[AnalyzerContribution, ...],
    ) -> RepositoryIntelligenceProfile:
        merged: dict[str, list[Any]] = {field: [] for field in _MERGED_FIELDS}
        infrastructure: InfrastructureHints | None = None
        naming_profile = None
        confidences = []
        for contribution in contributions:
            for field in _MERGED_FIELDS:
                merged[field].extend(getattr(contribution, field))
            if infrastructure is None and contribution.infrastructure is not None:
                infrastructure = contribution.infrastructure
            if naming_profile is None and contribution.naming_profile is not None:
                naming_profile = contribution.naming_profile
            if contribution.confidence is not None:
                confidences.append(contribution.confidence)

        languages = tuple(merged["languages"])
        frameworks = tuple(merged["frameworks"])
        return RepositoryIntelligenceProfile(
            repository_name=evidence.repository_name,
            root_path=evidence.root_path,
            is_git_repository=evidence.is_git_repository,
            file_count=evidence.file_count,
            folder_structure=self._folders(evidence),
            languages=languages,
            frameworks=frameworks,
            package_managers=tuple(merged["package_managers"]),
            services=tuple(merged["services"]),
            technologies=(*languages, *frameworks),
            databases=tuple(merged["databases"]),
            cloud_providers=tuple(merged["cloud_providers"]),
            cicd=tuple(merged["cicd"]),
            documentation=tuple(merged["documentation"]),
            mcp_configurations=tuple(merged["mcp_configurations"]),
            infrastructure=infrastructure or InfrastructureHints(),
            naming_profile=naming_profile,
            secret_locations=tuple(merged["secret_locations"]),
            risk_areas=tuple(merged["risk_areas"]),
            confidence_metadata=tuple(confidences),
            truncated=evidence.truncated,
        )

    @staticmethod
    def _folders(evidence: RepositoryEvidence) -> tuple[str, ...]:
        return tuple(
            sorted(
                {
                    str(PurePath(path).parent)
                    for path in evidence.paths
                    if str(PurePath(path).parent) != "."
                }
            )
        )
