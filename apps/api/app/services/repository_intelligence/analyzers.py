# Purpose: define the analyzer contract and the deterministic analyzers that read one
#   RepositoryEvidence bundle and contribute part of a repository intelligence profile.
# Responsibilities: single-responsibility detection (languages, frameworks, infrastructure, and so
#   on) with no filesystem access and no source retention. Dependencies: domain contracts, the
#   evidence bundle, and the existing naming inference engine.
from __future__ import annotations

from pathlib import PurePath
from typing import Protocol, runtime_checkable

from app.models.domain.base import DomainModel
from app.models.domain.intelligence import (
    AnalyzerConfidence,
    InfrastructureHints,
    IntelligenceRiskArea,
    NamingProfile,
    SecretLocation,
)
from app.models.domain.organization import RiskLevel, TechnologyEvidence
from app.services.repository_intelligence.evidence import FileEntry, RepositoryEvidence
from app.services.repository_intelligence.naming import (
    NamingCorpus,
    NamingPatternInferenceEngine,
)

_LANGUAGES: dict[str, str] = {
    ".py": "Python",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".js": "JavaScript",
    ".go": "Go",
    ".java": "Java",
    ".rb": "Ruby",
    ".rs": "Rust",
    ".cs": "C#",
}
_FRAMEWORK_FILES: dict[str, str] = {
    "next.config.js": "Next.js",
    "next.config.ts": "Next.js",
    "manage.py": "Django",
}
_PACKAGE_MANAGERS: tuple[tuple[str, str], ...] = (
    ("package.json", "npm"),
    ("pnpm-lock.yaml", "pnpm"),
    ("poetry.lock", "Poetry"),
    ("requirements.txt", "pip"),
    ("go.mod", "Go modules"),
)
_DATABASES: dict[str, str] = {
    "postgres": "PostgreSQL",
    "mysql": "MySQL",
    "sqlite": "SQLite",
    "mongodb": "MongoDB",
}
_CLOUD: dict[str, str] = {"aws": "AWS", "azure": "Azure", "google_cloud": "GCP", "gcp": "GCP"}
_SECRET_MARKERS: tuple[str, ...] = (".env", "secrets", "credential", "apikey", "api_key")
_SERVICE_SUFFIXES: tuple[str, ...] = ("-service", "_service", "-worker", "_worker")
_DOC_PREFIXES: tuple[str, ...] = ("readme", "runbook", "architecture")
_DOC_SUFFIXES: frozenset[str] = frozenset({".md", ".rst"})


class AnalyzerContribution(DomainModel):
    """Immutable partial profile emitted by one analyzer.

    Every field defaults to empty so the profile builder can fold contributions by
    concatenation, letting a new analyzer extend the pipeline without builder changes.
    """

    languages: tuple[TechnologyEvidence, ...] = ()
    frameworks: tuple[TechnologyEvidence, ...] = ()
    package_managers: tuple[TechnologyEvidence, ...] = ()
    services: tuple[TechnologyEvidence, ...] = ()
    databases: tuple[TechnologyEvidence, ...] = ()
    cloud_providers: tuple[TechnologyEvidence, ...] = ()
    cicd: tuple[TechnologyEvidence, ...] = ()
    documentation: tuple[TechnologyEvidence, ...] = ()
    mcp_configurations: tuple[TechnologyEvidence, ...] = ()
    infrastructure: InfrastructureHints | None = None
    secret_locations: tuple[SecretLocation, ...] = ()
    risk_areas: tuple[IntelligenceRiskArea, ...] = ()
    naming_profile: NamingProfile | None = None
    confidence: AnalyzerConfidence | None = None


@runtime_checkable
class RepositoryAnalyzer(Protocol):
    """Contract for a pure evidence-to-contribution detector.

    Implementations must not touch the filesystem or retain source; they read only the
    provided evidence bundle. ``name`` labels the analyzer's confidence metadata.
    """

    name: str

    def analyze(self, evidence: RepositoryEvidence) -> AnalyzerContribution: ...


def _evidence(category: str, name: str) -> TechnologyEvidence:
    return TechnologyEvidence(name=name, confidence=0.8, evidence=(category,))


def _confidence(name: str, count: int, value: float = 0.8) -> AnalyzerConfidence | None:
    if count == 0:
        return None
    return AnalyzerConfidence(analyzer=name, confidence=value, evidence_count=count)


def _detect(values: tuple[str, ...], patterns: dict[str, str]) -> tuple[str, ...]:
    text = "\n".join(values).lower()
    return tuple(sorted({name for pattern, name in patterns.items() if pattern in text}))


def _service_stems(files: tuple[FileEntry, ...]) -> tuple[str, ...]:
    return tuple(
        PurePath(entry.name).stem
        for entry in files
        if PurePath(entry.name).stem.endswith(_SERVICE_SUFFIXES)
    )


class LanguageAnalyzer:
    """Maps file extensions to programming languages."""

    name = "language"

    def analyze(self, evidence: RepositoryEvidence) -> AnalyzerContribution:
        languages = tuple(
            _evidence("language", name)
            for suffix, name in _LANGUAGES.items()
            if evidence.extension_counts.get(suffix)
        )
        return AnalyzerContribution(
            languages=languages, confidence=_confidence(self.name, len(languages))
        )


class FrameworkAnalyzer:
    """Detects frameworks from signature files and text fragments."""

    name = "framework"

    def analyze(self, evidence: RepositoryEvidence) -> AnalyzerContribution:
        filenames = {entry.name.lower() for entry in evidence.files}
        names = {name for marker, name in _FRAMEWORK_FILES.items() if marker in filenames}
        if any("fastapi" in fragment.lower() for fragment in evidence.text_fragments):
            names.add("FastAPI")
        frameworks = tuple(_evidence("framework", name) for name in sorted(names))
        return AnalyzerContribution(
            frameworks=frameworks, confidence=_confidence(self.name, len(frameworks))
        )


class PackageManagerAnalyzer:
    """Detects package managers from lockfile and manifest names."""

    name = "package_manager"

    def analyze(self, evidence: RepositoryEvidence) -> AnalyzerContribution:
        filenames = {entry.name for entry in evidence.files}
        managers = tuple(
            _evidence("package_manager", label)
            for marker, label in _PACKAGE_MANAGERS
            if marker in filenames
        )
        return AnalyzerContribution(
            package_managers=managers, confidence=_confidence(self.name, len(managers))
        )


class ServiceAnalyzer:
    """Extracts service and worker names from file stems."""

    name = "service"

    def analyze(self, evidence: RepositoryEvidence) -> AnalyzerContribution:
        services = tuple(_evidence("service", stem) for stem in _service_stems(evidence.files))
        return AnalyzerContribution(
            services=services, confidence=_confidence(self.name, len(services))
        )


class DatabaseAnalyzer:
    """Detects database technologies referenced in text fragments."""

    name = "database"

    def analyze(self, evidence: RepositoryEvidence) -> AnalyzerContribution:
        databases = tuple(
            _evidence("database", name) for name in _detect(evidence.text_fragments, _DATABASES)
        )
        return AnalyzerContribution(
            databases=databases, confidence=_confidence(self.name, len(databases))
        )


class CloudAnalyzer:
    """Detects cloud provider hints across fragments and paths."""

    name = "cloud"

    def analyze(self, evidence: RepositoryEvidence) -> AnalyzerContribution:
        providers = tuple(
            _evidence("cloud", name)
            for name in _detect(evidence.text_fragments + evidence.paths, _CLOUD)
        )
        return AnalyzerContribution(
            cloud_providers=providers, confidence=_confidence(self.name, len(providers))
        )


class InfrastructureAnalyzer:
    """Detects Docker, Terraform, and Kubernetes infrastructure files."""

    name = "infrastructure"

    def analyze(self, evidence: RepositoryEvidence) -> AnalyzerContribution:
        docker: list[str] = []
        terraform: list[str] = []
        kubernetes: list[str] = []
        for entry in evidence.files:
            lowered = entry.path.lower()
            if entry.name == "Dockerfile":
                docker.append(entry.path)
            if entry.suffix == ".tf":
                terraform.append(entry.path)
            if "k8s" in lowered or "kubernetes" in lowered:
                kubernetes.append(entry.path)
        count = len(docker) + len(terraform) + len(kubernetes)
        hints = InfrastructureHints(
            docker_files=tuple(docker),
            kubernetes_files=tuple(kubernetes),
            terraform_files=tuple(terraform),
        )
        return AnalyzerContribution(infrastructure=hints, confidence=_confidence(self.name, count))


class CicdAnalyzer:
    """Detects continuous integration and delivery configuration.

    Fills a previously unpopulated profile field; recognizes the common providers by their
    canonical file locations without reading file contents.
    """

    name = "cicd"

    def analyze(self, evidence: RepositoryEvidence) -> AnalyzerContribution:
        found: set[str] = set()
        for entry in evidence.files:
            lowered_path = entry.path.replace("\\", "/").lower()
            lowered_name = entry.name.lower()
            if lowered_path.startswith(".github/workflows/") and entry.suffix in {".yml", ".yaml"}:
                found.add("GitHub Actions")
            if lowered_name == ".gitlab-ci.yml":
                found.add("GitLab CI")
            if entry.name == "Jenkinsfile":
                found.add("Jenkins")
            if lowered_path.startswith(".circleci/"):
                found.add("CircleCI")
            if lowered_name in {"azure-pipelines.yml", "azure-pipelines.yaml"}:
                found.add("Azure Pipelines")
            if lowered_name == ".drone.yml":
                found.add("Drone")
            if lowered_name == "bitbucket-pipelines.yml":
                found.add("Bitbucket Pipelines")
            if lowered_name == ".travis.yml":
                found.add("Travis CI")
        cicd = tuple(_evidence("cicd", name) for name in sorted(found))
        return AnalyzerContribution(cicd=cicd, confidence=_confidence(self.name, len(cicd)))


class SecretPatternAnalyzer:
    """Flags secret-bearing configuration paths and their exposure risk."""

    name = "secret_pattern"

    def analyze(self, evidence: RepositoryEvidence) -> AnalyzerContribution:
        locations: list[SecretLocation] = []
        risks: list[IntelligenceRiskArea] = []
        for entry in evidence.files:
            lowered = entry.path.lower()
            if any(marker in lowered for marker in _SECRET_MARKERS):
                locations.append(SecretLocation(path=entry.path, patterns=()))
                risks.append(
                    IntelligenceRiskArea(
                        category="secret_exposure_surface",
                        severity=RiskLevel.MEDIUM,
                        description="Potential secret-bearing configuration path.",
                        paths=(entry.path,),
                    )
                )
        return AnalyzerContribution(
            secret_locations=tuple(locations),
            risk_areas=tuple(risks),
            confidence=_confidence(self.name, len(locations)),
        )


class DocumentationAnalyzer:
    """Collects documentation surfaces up to a bounded count."""

    name = "documentation"
    _limit = 20

    def analyze(self, evidence: RepositoryEvidence) -> AnalyzerContribution:
        docs: list[TechnologyEvidence] = []
        for entry in evidence.files:
            if entry.name.lower().startswith(_DOC_PREFIXES) or entry.suffix in _DOC_SUFFIXES:
                docs.append(_evidence("documentation", entry.path))
        bounded = tuple(docs[: self._limit])
        return AnalyzerContribution(
            documentation=bounded, confidence=_confidence(self.name, len(bounded))
        )


class McpAnalyzer:
    """Detects the presence of MCP configuration surfaces."""

    name = "mcp"

    def analyze(self, evidence: RepositoryEvidence) -> AnalyzerContribution:
        present = any("mcp" in entry.path.lower() for entry in evidence.files)
        mcp = (_evidence("mcp_configuration", "MCP"),) if present else ()
        return AnalyzerContribution(
            mcp_configurations=mcp, confidence=_confidence(self.name, len(mcp))
        )


class NamingAnalyzer:
    """Adapts the naming inference engine into the analyzer contract."""

    name = "naming"

    def __init__(self, engine: NamingPatternInferenceEngine | None = None) -> None:
        self._engine = engine or NamingPatternInferenceEngine()

    def analyze(self, evidence: RepositoryEvidence) -> AnalyzerContribution:
        profile = self._engine.infer(
            NamingCorpus(
                file_paths=evidence.paths,
                text_fragments=evidence.text_fragments,
                service_names=_service_stems(evidence.files),
            )
        )
        return AnalyzerContribution(
            naming_profile=profile,
            confidence=AnalyzerConfidence(
                analyzer=self.name,
                confidence=profile.confidence,
                evidence_count=evidence.file_count,
            ),
        )


def default_analyzers() -> tuple[RepositoryAnalyzer, ...]:
    """Return the standard analyzer pipeline in deterministic execution order."""
    return (
        LanguageAnalyzer(),
        FrameworkAnalyzer(),
        PackageManagerAnalyzer(),
        ServiceAnalyzer(),
        DatabaseAnalyzer(),
        CloudAnalyzer(),
        InfrastructureAnalyzer(),
        CicdAnalyzer(),
        SecretPatternAnalyzer(),
        DocumentationAnalyzer(),
        McpAnalyzer(),
        NamingAnalyzer(),
    )
