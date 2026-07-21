# Purpose: map the bounded RepositorySignals input into an in-memory RepositoryIntelligenceProfile
#   so the existing deterministic context + placement engines can run WITHOUT any filesystem scan.
# Responsibilities: pure, deterministic translation. Path-like strings become descriptive evidence
#   only — never opened. No I/O, no persistence.
# Dependencies: intelligence + organization domain models, analysis_signals contract.
from __future__ import annotations

from app.models.domain.analysis_signals import RepositorySignals
from app.models.domain.intelligence import (
    InfrastructureHints,
    NamingCategory,
    NamingConvention,
    NamingProfile,
    NamingStyle,
    RepositoryIntelligenceProfile,
    SecretLocation,
    Separator,
    VocabularyTerm,
)
from app.models.domain.organization import TechnologyEvidence

_IN_MEMORY_ROOT = "signals://in-memory"  # descriptive only; never opened


def _evidence(paths: tuple[str, ...], limit: int = 20) -> tuple[str, ...]:
    # Dedup while preserving order, bounded — evidence is provenance, not a filesystem handle.
    seen: dict[str, None] = {}
    for p in paths:
        if p and p not in seen:
            seen[p] = None
        if len(seen) >= limit:
            break
    return tuple(seen.keys())


def _tech(name: str, confidence: float, evidence: tuple[str, ...]) -> TechnologyEvidence:
    return TechnologyEvidence(name=name, confidence=confidence, evidence=_evidence(evidence))


def _naming_profile(signals: RepositorySignals) -> NamingProfile | None:
    naming = signals.naming_patterns
    if naming is None:
        return None
    terms: list[VocabularyTerm] = []
    seen: set[str] = set()
    for source in (naming.domain_terms, naming.entity_names, naming.team_terms):
        for term in source:
            key = term.lower()
            if key not in seen:
                seen.add(key)
                terms.append(VocabularyTerm(value=term, support=1))
    conventions: list[NamingConvention] = []
    if naming.environment_terms:
        conventions.append(
            NamingConvention(
                category=NamingCategory.ENVIRONMENT_VARIABLE,
                style=NamingStyle.SCREAMING_SNAKE,
                separator=Separator.UNDERSCORE,
                support=len(naming.environment_terms),
                confidence=min(1.0, 0.4 + 0.1 * len(naming.environment_terms)),
                samples=tuple(naming.environment_terms[:5]),
            )
        )
    if any(source for source in (terms, naming.prefixes, naming.suffixes, conventions)):
        return NamingProfile(
            naming_style=tuple(conventions),
            common_prefixes=tuple(naming.prefixes[:20]),
            common_suffixes=tuple(naming.suffixes[:20]),
            vocabulary=tuple(terms[:50]),
            separators=(),
            confidence=min(1.0, 0.3 + 0.05 * len(terms)),
        )
    return None


def _infrastructure(signals: RepositorySignals) -> InfrastructureHints:
    infra = signals.infrastructure
    if infra is None:
        return InfrastructureHints()
    docker = _evidence(tuple(infra.container_tools) + tuple(infra.deployment_paths))
    kube = _evidence(tuple(infra.orchestration))
    terraform = _evidence(tuple(infra.infrastructure_as_code))
    return InfrastructureHints(
        docker_files=docker, kubernetes_files=kube, terraform_files=terraform
    )


def signals_to_profile(
    signals: RepositorySignals, *, repository_name: str = "signals-preview"
) -> RepositoryIntelligenceProfile:
    """Deterministically translate structured signals into an intelligence profile (no scan)."""
    languages = tuple(
        _tech(s.name, s.confidence if s.confidence is not None else 0.7, s.representative_paths)
        for s in signals.languages
    )
    frameworks = tuple(_tech(s.name, 0.7, s.representative_paths) for s in signals.frameworks)
    package_managers = tuple(_tech(s.name, 0.8, s.manifest_paths) for s in signals.package_managers)
    services = tuple(
        _tech(s.name, 0.7, tuple(s.representative_paths) + tuple(s.dependencies))
        for s in signals.services
    )
    databases = tuple(
        _tech(s.engine, 0.7, tuple(s.schema_or_migration_paths) + tuple(s.data_domain_terms))
        for s in signals.databases
    )
    # AI surfaces (RAG/MCP) drive context.ai_exposure via mcp_configurations.
    ai = tuple(
        _tech(
            s.surface_type,
            s.confidence if s.confidence is not None else 0.7,
            tuple(p for p in (s.path_or_resource, s.provider_or_framework) if p),
        )
        for s in signals.ai_surfaces
    )
    # Documentation TechnologyEvidence carries the doc paths as evidence for placement discovery.
    documentation: list[TechnologyEvidence] = []
    if signals.documentation is not None:
        doc = signals.documentation
        for label, paths in (
            ("runbook", doc.runbook_paths),
            ("architecture", doc.architecture_paths),
            ("operational", doc.operational_paths),
            ("support", doc.support_paths),
            ("policy", doc.policy_paths),
        ):
            if paths:
                documentation.append(_tech(label, 0.7, tuple(paths)))
    cicd: tuple[TechnologyEvidence, ...] = ()
    cloud: tuple[TechnologyEvidence, ...] = ()
    if signals.infrastructure is not None:
        cicd = tuple(_tech(name, 0.7, (name,)) for name in signals.infrastructure.ci_cd[:20])
        cloud = tuple(
            _tech(name, 0.7, (name,)) for name in signals.infrastructure.cloud_indicators[:20]
        )
    secret_locations = tuple(
        SecretLocation(path=s.path, patterns=(s.category,) if s.category else ())
        for s in signals.secret_locations
    )
    file_count = sum(
        (s.evidence_count or len(s.representative_paths)) for s in signals.languages
    ) or len(languages)

    return RepositoryIntelligenceProfile(
        repository_name=repository_name[:256] or "signals-preview",
        root_path=_IN_MEMORY_ROOT,
        is_git_repository=False,
        file_count=max(0, file_count),
        folder_structure=(),
        languages=languages,
        frameworks=frameworks,
        package_managers=package_managers,
        services=services,
        technologies=frameworks + services,
        databases=databases,
        cloud_providers=cloud,
        cicd=cicd,
        documentation=tuple(documentation),
        mcp_configurations=ai,
        infrastructure=_infrastructure(signals),
        naming_profile=_naming_profile(signals),
        secret_locations=secret_locations,
        risk_areas=(),
        confidence_metadata=(),
        truncated=False,
    )
