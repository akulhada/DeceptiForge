# Purpose: deterministic repository-path classification and agent-exposure/severity mapping.
# Responsibilities: classify a normalized path into a PathClass from decoy membership, name-pattern
#   sensitivity, and the session scope; map a violation type to an AI-agent exposure category; and
#   assign incident severity deterministically. GPT never classifies or scores. Pure.
from __future__ import annotations

from app.models.domain.agent_sensor import (
    AgentExposure,
    PathClass,
    ScopeViolationType,
)
from app.models.domain.operations import Severity
from app.services.agent_sensor.paths import path_matches

# Ordered (class, substrings) rules; first match wins. Substrings are matched case-insensitively
# against the normalized path.
_PATTERN_RULES: tuple[tuple[PathClass, tuple[str, ...]], ...] = (
    (PathClass.CREDENTIAL, (".env", "secrets", "secret.", "credential", "id_rsa", ".pem", ".p12",
                            ".pfx", "private_key", ".key")),
    (PathClass.AUTHENTICATION, ("/auth/", "authentication", "oauth", "/login", "jwt", "session/",
                                "passport")),
    (PathClass.BILLING, ("billing", "payment", "invoice", "stripe", "subscription")),
    (PathClass.CUSTOMER_DATA, ("customer_data", "/pii", "personal_data", "gdpr", "customers/")),
    (PathClass.DEPLOYMENT, ("dockerfile", "/k8s/", "kubernetes", "terraform", "/helm/", "ansible",
                            ".github/workflows", "deploy/")),
    (PathClass.BUILD_OUTPUT, ("dist/", "build/", ".next/", "out/", "target/", "coverage/")),
    (PathClass.GENERATED, (".generated.", "__generated__", "_pb2", ".pb.go", ".g.dart")),
    (PathClass.SHARED_DEPENDENCY, ("node_modules/", "vendor/", "third_party/", "package-lock.json",
                                   "yarn.lock", "poetry.lock", "go.sum", "cargo.lock")),
)


def _top_dirs(path: str, n: int = 2) -> str:
    return "/".join(path.split("/")[:n])


def classify_path(
    normalized_path: str,
    *,
    allowed_paths: tuple[str, ...],
    decoy_paths: frozenset[str],
) -> PathClass:
    lower = normalized_path.lower()
    if lower in decoy_paths:
        return PathClass.DECOY
    for path_class, needles in _PATTERN_RULES:
        if any(needle in lower for needle in needles):
            return path_class
    for pattern in allowed_paths:
        if path_matches(pattern, normalized_path):
            return PathClass.TASK_RELEVANT
    # Adjacent: shares its top-two directories with an allowed path.
    prefix = _top_dirs(normalized_path)
    for pattern in allowed_paths:
        base = pattern[:-3] if pattern.endswith("/**") else pattern
        if _top_dirs(base) == prefix and prefix:
            return PathClass.ADJACENT
    return PathClass.UNRELATED


_EXPOSURE: dict[ScopeViolationType, AgentExposure] = {
    ScopeViolationType.DECOY_ASSET_TOUCH: AgentExposure.AI_AGENT_DECOY_TOUCH,
    ScopeViolationType.SENSITIVE_FILE_ACCESS: AgentExposure.AI_AGENT_SENSITIVE_EXPLORATION,
    ScopeViolationType.REPEATED_SENSITIVE_EXPLORATION: (
        AgentExposure.AI_AGENT_SENSITIVE_EXPLORATION
    ),
    ScopeViolationType.DESTRUCTIVE_ACTION_ATTEMPT: AgentExposure.AI_AGENT_DESTRUCTIVE_ATTEMPT,
    ScopeViolationType.UNAPPROVED_TOOL_USE: AgentExposure.AI_AGENT_POLICY_VIOLATION,
    ScopeViolationType.DEPENDENCY_CHANGE_OUTSIDE_SCOPE: AgentExposure.AI_AGENT_POLICY_VIOLATION,
    ScopeViolationType.CROSS_REPOSITORY_ACCESS: AgentExposure.AI_AGENT_CROSS_SURFACE_EXPOSURE,
    ScopeViolationType.UNEXPECTED_DATABASE_ACCESS: AgentExposure.AI_AGENT_CROSS_SURFACE_EXPOSURE,
    ScopeViolationType.UNEXPECTED_NETWORK_ACCESS: AgentExposure.AI_AGENT_CROSS_SURFACE_EXPOSURE,
    ScopeViolationType.UNEXPECTED_MCP_RESOURCE_ACCESS: (
        AgentExposure.AI_AGENT_CROSS_SURFACE_EXPOSURE
    ),
}


def exposure_for(violation_type: ScopeViolationType) -> AgentExposure:
    return _EXPOSURE.get(violation_type, AgentExposure.AI_AGENT_SCOPE_VIOLATION)


_ORDER = (Severity.INFO, Severity.LOW, Severity.MEDIUM, Severity.HIGH, Severity.CRITICAL)


def incident_severity(
    exposure: AgentExposure,
    *,
    violation_count: int,
    cross_surface: bool,
    modifications: bool,
) -> Severity:
    """Deterministic incident severity from category, repetition, cross-surface, and whether the
    agent actually modified/succeeded. GPT never assigns severity."""
    base = {
        AgentExposure.AI_AGENT_SCOPE_VIOLATION: Severity.LOW,
        AgentExposure.AI_AGENT_POLICY_VIOLATION: Severity.MEDIUM,
        AgentExposure.AI_AGENT_SENSITIVE_EXPLORATION: Severity.MEDIUM,
        AgentExposure.AI_AGENT_CROSS_SURFACE_EXPOSURE: Severity.HIGH,
        AgentExposure.AI_AGENT_DESTRUCTIVE_ATTEMPT: Severity.HIGH,
        AgentExposure.AI_AGENT_DECOY_TOUCH: Severity.HIGH,
    }[exposure]
    level = _ORDER.index(base)
    level += int(violation_count >= 3)
    level += int(cross_surface)
    level += int(modifications)
    return _ORDER[min(level, len(_ORDER) - 1)]
