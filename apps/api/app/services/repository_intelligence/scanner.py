"""Bounded local repository scanner that produces transport-neutral intelligence."""
from __future__ import annotations

import os
from collections import Counter
from pathlib import Path

from app.models.domain.intelligence import (
    AnalyzerConfidence,
    InfrastructureHints,
    IntelligenceRiskArea,
    RepositoryIntelligenceProfile,
    SecretLocation,
)
from app.models.domain.organization import RiskLevel, TechnologyEvidence
from app.services.repository_intelligence.naming import NamingCorpus, NamingPatternInferenceEngine

_SKIP = {".git", "node_modules", "vendor", "dist", "build", "__pycache__", ".venv"}
_LANGUAGES = {
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
_FRAMEWORK_FILES = {
    "next.config.js": "Next.js",
    "next.config.ts": "Next.js",
    "manage.py": "Django",
    "fastapi": "FastAPI",
}
_SECRET_NAMES = (".env", "secrets", "credential", "apikey", "api_key")
_MAX_FILES = 10_000
_MAX_TEXT_FILES = 200
_MAX_TEXT_BYTES = 20_000


class LocalRepositoryScanner:
    """Single-pass scanner with bounded text collection and no source persistence."""

    def __init__(self, naming_engine: NamingPatternInferenceEngine | None = None) -> None:
        self._naming_engine = naming_engine or NamingPatternInferenceEngine()

    def scan(self, root: Path) -> RepositoryIntelligenceProfile:
        root = root.resolve()
        paths: list[str] = []
        fragments: list[str] = []
        extensions: Counter[str] = Counter()
        docker: list[str] = []
        terraform: list[str] = []
        kubernetes: list[str] = []
        docs: list[TechnologyEvidence] = []
        secret_locations: list[SecretLocation] = []
        truncated = False
        for directory, dirnames, filenames in os.walk(root):
            dirnames[:] = [name for name in dirnames if name not in _SKIP]
            for filename in filenames:
                if len(paths) >= _MAX_FILES:
                    truncated = True
                    break
                path = Path(directory, filename)
                relative = str(path.relative_to(root))
                paths.append(relative)
                extensions[path.suffix.lower()] += 1
                lowered = relative.lower()
                if filename == "Dockerfile":
                    docker.append(relative)
                if path.suffix == ".tf":
                    terraform.append(relative)
                if "k8s" in lowered or "kubernetes" in lowered:
                    kubernetes.append(relative)
                if filename.lower().startswith(
                    ("readme", "runbook", "architecture")
                ) or path.suffix.lower() in {".md", ".rst"}:
                    docs.append(_evidence("documentation", relative))
                if any(marker in lowered for marker in _SECRET_NAMES):
                    secret_locations.append(SecretLocation(path=relative, patterns=()))
                if len(fragments) < _MAX_TEXT_FILES and path.suffix.lower() in {
                    ".py",
                    ".ts",
                    ".tsx",
                    ".js",
                    ".json",
                    ".yaml",
                    ".yml",
                    ".tf",
                    ".sql",
                }:
                    try:
                        fragments.append(
                            path.read_text(encoding="utf-8", errors="ignore")[:_MAX_TEXT_BYTES]
                        )
                    except OSError:
                        continue
            if truncated:
                break
        languages = tuple(
            _evidence("language", name) for suffix, name in _LANGUAGES.items() if extensions[suffix]
        )
        framework_names = {
            name
            for filename, name in _FRAMEWORK_FILES.items()
            if filename in {Path(path).name.lower() for path in paths}
        }
        framework_names.update(
            {"FastAPI"} if any("fastapi" in text.lower() for text in fragments) else set()
        )
        frameworks = tuple(_evidence("framework", name) for name in sorted(framework_names))
        databases = tuple(
            _evidence("database", name)
            for name in _detect(
                fragments,
                {
                    "postgres": "PostgreSQL",
                    "mysql": "MySQL",
                    "sqlite": "SQLite",
                    "mongodb": "MongoDB",
                },
            )
        )
        cloud = tuple(
            _evidence("cloud", name)
            for name in _detect(
                fragments + paths,
                {"aws": "AWS", "azure": "Azure", "google_cloud": "GCP", "gcp": "GCP"},
            )
        )
        services = tuple(
            _evidence("service", Path(path).stem)
            for path in paths
            if Path(path).stem.endswith(("-service", "_service", "-worker", "_worker"))
        )
        package_managers = tuple(
            _evidence("package_manager", name)
            for marker, name in (
                ("package.json", "npm"),
                ("pnpm-lock.yaml", "pnpm"),
                ("poetry.lock", "Poetry"),
                ("requirements.txt", "pip"),
                ("go.mod", "Go modules"),
            )
            if marker in {Path(path).name for path in paths}
        )
        mcp = (
            (_evidence("mcp_configuration", "MCP"),)
            if any("mcp" in path.lower() for path in paths)
            else ()
        )
        naming = self._naming_engine.infer(
            NamingCorpus(
                file_paths=tuple(paths),
                text_fragments=tuple(fragments),
                service_names=tuple(item.name for item in services),
            )
        )
        risks = tuple(
            IntelligenceRiskArea(
                category="secret_exposure_surface",
                severity=RiskLevel.MEDIUM,
                description="Potential secret-bearing configuration path.",
                paths=(item.path,),
            )
            for item in secret_locations
        )
        return RepositoryIntelligenceProfile(
            repository_name=root.name,
            root_path=str(root),
            is_git_repository=(root / ".git").exists(),
            file_count=len(paths),
            folder_structure=tuple(
                sorted({str(Path(path).parent) for path in paths if str(Path(path).parent) != "."})
            ),
            languages=languages,
            frameworks=frameworks,
            package_managers=package_managers,
            services=services,
            technologies=(*languages, *frameworks),
            databases=databases,
            cloud_providers=cloud,
            documentation=tuple(docs[:20]),
            mcp_configurations=mcp,
            infrastructure=InfrastructureHints(
                docker_files=tuple(docker),
                kubernetes_files=tuple(kubernetes),
                terraform_files=tuple(terraform),
            ),
            naming_profile=naming,
            secret_locations=tuple(secret_locations),
            risk_areas=risks,
            confidence_metadata=(
                AnalyzerConfidence(
                    analyzer="local_repository_scanner",
                    confidence=0.7 if paths else 0.0,
                    evidence_count=len(paths),
                ),
            ),
            truncated=truncated,
        )


def _evidence(category: str, name: str) -> TechnologyEvidence:
    return TechnologyEvidence(name=name, confidence=0.8, evidence=(category,))


def _detect(values: list[str], patterns: dict[str, str]) -> tuple[str, ...]:
    text = "\n".join(values).lower()
    return tuple(sorted({name for pattern, name in patterns.items() if pattern in text}))
