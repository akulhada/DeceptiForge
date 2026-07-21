# Purpose: the shared, bounded RepositorySignals input contract for the Interactive Demo Lab.
# Responsibilities: accept structured, fictional repository signals (never paths to scan or code to
#   run), enforce hard size/length/collection bounds before analysis, and drop-and-report unknown
#   fields. Path-like strings here are DESCRIPTIVE METADATA ONLY — the backend never opens them.
# Dependencies: pydantic. No filesystem, no network, no persistence.
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

# ---- hard bounds (enforced before any analysis runs) ---------------------------------------------
MAX_COLLECTION = 100  # entries per top-level collection
MAX_STRING = 256  # generic string length
MAX_PATH = 512  # path-like descriptive string length
MAX_PATHS_PER_ENTRY = 25  # representative_paths etc. per entry
MAX_NAMING_TERMS = 200  # entries per naming-pattern list
MAX_TOTAL_PATHS = 2000  # aggregate representative paths across the whole request


class SignalModel(BaseModel):
    """Lenient-but-bounded base for user-supplied signals.

    Unknown fields are ignored (not an error) so the JSON editor stays forgiving; the endpoint
    reports which top-level keys were ignored. Not frozen/strict — this is untrusted input, coerced
    into a safe shape, never executed.
    """

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)


_Str = Field(min_length=1, max_length=MAX_STRING)
_Paths = Field(default=(), max_length=MAX_PATHS_PER_ENTRY)


class LanguageSignal(SignalModel):
    name: str = _Str
    confidence: float | None = Field(default=None, ge=0, le=1)
    evidence_count: int | None = Field(default=None, ge=0, le=1_000_000)
    representative_paths: tuple[str, ...] = _Paths


class FrameworkSignal(SignalModel):
    name: str = _Str
    category: str | None = Field(default=None, max_length=MAX_STRING)
    representative_paths: tuple[str, ...] = _Paths


class PackageManagerSignal(SignalModel):
    name: str = _Str
    manifest_paths: tuple[str, ...] = _Paths


class ServiceSignal(SignalModel):
    name: str = _Str
    service_type: str | None = Field(default=None, max_length=MAX_STRING)
    representative_paths: tuple[str, ...] = _Paths
    dependencies: tuple[str, ...] = Field(default=(), max_length=MAX_PATHS_PER_ENTRY)


class NamingPatternSignal(SignalModel):
    entity_names: tuple[str, ...] = Field(default=(), max_length=MAX_NAMING_TERMS)
    prefixes: tuple[str, ...] = Field(default=(), max_length=MAX_NAMING_TERMS)
    suffixes: tuple[str, ...] = Field(default=(), max_length=MAX_NAMING_TERMS)
    environment_terms: tuple[str, ...] = Field(default=(), max_length=MAX_NAMING_TERMS)
    team_terms: tuple[str, ...] = Field(default=(), max_length=MAX_NAMING_TERMS)
    domain_terms: tuple[str, ...] = Field(default=(), max_length=MAX_NAMING_TERMS)


class InfrastructureSignal(SignalModel):
    container_tools: tuple[str, ...] = Field(default=(), max_length=MAX_PATHS_PER_ENTRY)
    orchestration: tuple[str, ...] = Field(default=(), max_length=MAX_PATHS_PER_ENTRY)
    cloud_indicators: tuple[str, ...] = Field(default=(), max_length=MAX_PATHS_PER_ENTRY)
    ci_cd: tuple[str, ...] = Field(default=(), max_length=MAX_PATHS_PER_ENTRY)
    infrastructure_as_code: tuple[str, ...] = Field(default=(), max_length=MAX_PATHS_PER_ENTRY)
    deployment_paths: tuple[str, ...] = _Paths


class DatabaseSignal(SignalModel):
    engine: str = _Str
    usage: str | None = Field(default=None, max_length=MAX_STRING)
    schema_or_migration_paths: tuple[str, ...] = _Paths
    data_domain_terms: tuple[str, ...] = Field(default=(), max_length=MAX_NAMING_TERMS)


class DocumentationSignal(SignalModel):
    runbook_paths: tuple[str, ...] = _Paths
    architecture_paths: tuple[str, ...] = _Paths
    operational_paths: tuple[str, ...] = _Paths
    support_paths: tuple[str, ...] = _Paths
    policy_paths: tuple[str, ...] = _Paths


class SecretLocationSignal(SignalModel):
    path: str = Field(min_length=1, max_length=MAX_PATH)
    category: str | None = Field(default=None, max_length=MAX_STRING)
    confidence: float | None = Field(default=None, ge=0, le=1)
    source_type: str | None = Field(default=None, max_length=MAX_STRING)


class AiSurfaceSignal(SignalModel):
    surface_type: str = _Str
    path_or_resource: str | None = Field(default=None, max_length=MAX_PATH)
    provider_or_framework: str | None = Field(default=None, max_length=MAX_STRING)
    confidence: float | None = Field(default=None, ge=0, le=1)


class RepositorySignals(SignalModel):
    """Top-level structured repository signals. Every field optional with a safe empty default.

    Unknown top-level keys are retained (extra="allow") ONLY so the endpoint can report them as
    ignored; they never influence analysis. Nested models still drop unknowns silently.
    """

    model_config = ConfigDict(extra="allow", str_strip_whitespace=True)

    languages: tuple[LanguageSignal, ...] = Field(default=(), max_length=MAX_COLLECTION)
    frameworks: tuple[FrameworkSignal, ...] = Field(default=(), max_length=MAX_COLLECTION)
    package_managers: tuple[PackageManagerSignal, ...] = Field(
        default=(), max_length=MAX_COLLECTION
    )
    services: tuple[ServiceSignal, ...] = Field(default=(), max_length=MAX_COLLECTION)
    naming_patterns: NamingPatternSignal | None = None
    infrastructure: InfrastructureSignal | None = None
    databases: tuple[DatabaseSignal, ...] = Field(default=(), max_length=MAX_COLLECTION)
    documentation: DocumentationSignal | None = None
    secret_locations: tuple[SecretLocationSignal, ...] = Field(
        default=(), max_length=MAX_COLLECTION
    )
    ai_surfaces: tuple[AiSurfaceSignal, ...] = Field(default=(), max_length=MAX_COLLECTION)


# The recognized top-level signal categories — used to compute "ignored/unknown fields".
KNOWN_TOP_LEVEL_FIELDS: frozenset[str] = frozenset(RepositorySignals.model_fields.keys())


def total_representative_paths(signals: RepositorySignals) -> int:
    """Aggregate path-like references across the request (bounded by MAX_TOTAL_PATHS)."""
    total = 0
    for lang in signals.languages:
        total += len(lang.representative_paths)
    for fw in signals.frameworks:
        total += len(fw.representative_paths)
    for pm in signals.package_managers:
        total += len(pm.manifest_paths)
    for svc in signals.services:
        total += len(svc.representative_paths)
    for db in signals.databases:
        total += len(db.schema_or_migration_paths)
    if signals.infrastructure is not None:
        total += len(signals.infrastructure.deployment_paths)
    if signals.documentation is not None:
        doc = signals.documentation
        total += (
            len(doc.runbook_paths)
            + len(doc.architecture_paths)
            + len(doc.operational_paths)
            + len(doc.support_paths)
            + len(doc.policy_paths)
        )
    total += len(signals.secret_locations)
    return total
