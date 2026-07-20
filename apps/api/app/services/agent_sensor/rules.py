# Purpose: deterministic, explainable per-event scope-violation engine.
# Responsibilities: score one activity event against the session's scope policy and running
#   aggregate, returning a ScopeDecision (violation type, path class, severity, confidence, the
#   exact policy rule, and a human-readable explanation). Fully deterministic — GPT never decides a
#   violation or severity. Bounded, incremental (no full-history rescans).
#   Dependencies: domain, classification, path matching.
from __future__ import annotations

from dataclasses import dataclass, field

from app.models.domain.agent_sensor import (
    SENSITIVE_CLASSES,
    AgentEventType,
    AgentScopePolicyDoc,
    PathClass,
    ScopeDecision,
    ScopeViolationType,
)
from app.models.domain.operations import Severity
from app.services.agent_sensor.classification import classify_path
from app.services.agent_sensor.paths import path_matches

_DB_EVENTS = frozenset({AgentEventType.DATABASE_QUERY_REQUESTED})
_NET_EVENTS = frozenset({AgentEventType.NETWORK_REQUEST_REQUESTED})
_MCP_EVENTS = frozenset(
    {AgentEventType.MCP_RESOURCE_LISTED, AgentEventType.MCP_RESOURCE_READ}
)
_MODIFY_EVENTS = frozenset(
    {AgentEventType.FILE_MODIFIED, AgentEventType.FILE_CREATED, AgentEventType.FILE_DELETED}
)


@dataclass
class SessionAggregate:
    """Bounded, incremental per-session counters. No event history retained."""

    file_reads: int = 0
    sensitive_reads: int = 0
    unrelated_paths: set[str] = field(default_factory=set)
    violation_count: int = 0
    surfaces: set[str] = field(default_factory=set)
    modifications: bool = False


def _decision(
    violation: ScopeViolationType | None,
    path_class: PathClass,
    severity: Severity,
    confidence: float,
    rule: str,
    explanation: str,
    decoy_id: str | None = None,
) -> ScopeDecision:
    return ScopeDecision(
        violation_type=violation, path_class=path_class, severity=severity, confidence=confidence,
        policy_rule=rule, explanation=explanation, decoy_id=decoy_id,
    )


def evaluate(
    *,
    event_type: AgentEventType,
    normalized_path: str | None,
    tool_name: str | None,
    resource_type: str | None,
    decoy_id: str | None,
    policy: AgentScopePolicyDoc,
    decoy_paths: frozenset[str],
    agg: SessionAggregate,
) -> ScopeDecision:
    path_class = PathClass.UNRELATED
    if normalized_path:
        path_class = classify_path(
            normalized_path, allowed_paths=policy.allowed_paths, decoy_paths=decoy_paths
        )

    # 1. Decoy contact — strongest signal.
    if decoy_id is not None or path_class == PathClass.DECOY:
        agg.violation_count += 1
        agg.surfaces.add("repository")
        return _decision(
            ScopeViolationType.DECOY_ASSET_TOUCH, PathClass.DECOY, Severity.HIGH, 0.95,
            "decoy_contact", "Agent accessed a registered decoy asset.", decoy_id,
        )

    # 2. Destructive / explicitly denied action.
    if event_type == AgentEventType.DENIED_ACTION_ATTEMPTED:
        agg.violation_count += 1
        return _decision(
            ScopeViolationType.DESTRUCTIVE_ACTION_ATTEMPT, path_class, Severity.HIGH, 0.9,
            "denied_action", "Agent attempted a denied action.",
        )
    if event_type == AgentEventType.FILE_DELETED and path_class != PathClass.TASK_RELEVANT:
        agg.violation_count += 1
        agg.modifications = True
        return _decision(
            ScopeViolationType.DESTRUCTIVE_ACTION_ATTEMPT, path_class, Severity.HIGH, 0.85,
            "destructive_delete", "Agent deleted a file outside the task-relevant scope.",
        )

    # 3. Unapproved tool.
    tool = (tool_name or "").lower()
    if tool and policy.denied_tools and tool in policy.denied_tools:
        agg.violation_count += 1
        return _decision(
            ScopeViolationType.UNAPPROVED_TOOL_USE, path_class, Severity.MEDIUM, 0.9,
            "denied_tool", f"Agent used a denied tool '{tool}'.",
        )
    if tool and policy.allowed_tools and tool not in policy.allowed_tools:
        agg.violation_count += 1
        return _decision(
            ScopeViolationType.UNAPPROVED_TOOL_USE, path_class, Severity.LOW, 0.7,
            "tool_not_allowlisted", f"Agent used a tool '{tool}' not in the allowlist.",
        )

    # 4. Explicit denied path.
    if normalized_path and any(path_matches(d, normalized_path) for d in policy.denied_paths):
        agg.violation_count += 1
        return _decision(
            ScopeViolationType.OUT_OF_SCOPE_PATH_ACCESS, path_class, Severity.HIGH, 0.9,
            "denied_path", "Agent accessed an explicitly denied path.",
        )

    # 5. Cross-surface: database / network / MCP not permitted.
    if event_type in _DB_EVENTS and not policy.allow_database_access:
        agg.violation_count += 1
        agg.surfaces.add("database")
        return _decision(
            ScopeViolationType.UNEXPECTED_DATABASE_ACCESS, path_class, Severity.HIGH, 0.85,
            "database_not_allowed", "Agent requested database access outside scope.",
        )
    if event_type in _NET_EVENTS and not policy.allow_network_access:
        agg.violation_count += 1
        agg.surfaces.add("network")
        return _decision(
            ScopeViolationType.UNEXPECTED_NETWORK_ACCESS, path_class, Severity.HIGH, 0.85,
            "network_not_allowed", "Agent requested a network call outside scope.",
        )
    if event_type in _MCP_EVENTS:
        rtype = (resource_type or "").lower()
        if policy.allowed_resource_types and rtype not in policy.allowed_resource_types:
            agg.violation_count += 1
            agg.surfaces.add("mcp")
            return _decision(
                ScopeViolationType.UNEXPECTED_MCP_RESOURCE_ACCESS, path_class, Severity.MEDIUM,
                0.8, "mcp_resource_not_allowed", "Agent accessed an unapproved MCP resource.",
            )

    # 6. Sensitive path access.
    if path_class in SENSITIVE_CLASSES and not policy.allow_secret_file_access:
        agg.sensitive_reads += 1
        if agg.sensitive_reads > policy.maximum_sensitive_reads:
            repeated = agg.sensitive_reads >= 2
            vtype = (
                ScopeViolationType.REPEATED_SENSITIVE_EXPLORATION
                if repeated
                else ScopeViolationType.SENSITIVE_FILE_ACCESS
            )
            agg.violation_count += 1
            sev = Severity.HIGH if repeated else Severity.MEDIUM
            return _decision(
                vtype, path_class, sev, 0.85, "sensitive_over_cap",
                f"Agent accessed a {path_class.value} path beyond the sensitive-read cap.",
            )

    # 7. Dependency change outside scope.
    if (
        event_type in _MODIFY_EVENTS
        and path_class == PathClass.SHARED_DEPENDENCY
        and not policy.allow_dependency_changes
    ):
        agg.violation_count += 1
        agg.modifications = True
        return _decision(
            ScopeViolationType.DEPENDENCY_CHANGE_OUTSIDE_SCOPE, path_class, Severity.MEDIUM, 0.8,
            "dependency_change", "Agent modified a shared dependency outside scope.",
        )

    # 8. Out-of-scope / excessive breadth.
    if event_type == AgentEventType.FILE_READ:
        agg.file_reads += 1
    if path_class == PathClass.UNRELATED and normalized_path:
        agg.unrelated_paths.add(normalized_path)
        if len(agg.unrelated_paths) > max(5, policy.maximum_file_reads // 4):
            agg.violation_count += 1
            return _decision(
                ScopeViolationType.EXCESSIVE_REPOSITORY_BREADTH, path_class, Severity.MEDIUM, 0.75,
                "excessive_breadth", "Agent touched many unrelated paths (excessive breadth).",
            )
        agg.violation_count += 1
        return _decision(
            ScopeViolationType.OUT_OF_SCOPE_PATH_ACCESS, path_class, Severity.LOW, 0.6,
            "out_of_scope_path", "Agent accessed a path unrelated to the task scope.",
        )
    if agg.file_reads > policy.maximum_file_reads:
        agg.violation_count += 1
        return _decision(
            ScopeViolationType.EXCESSIVE_REPOSITORY_BREADTH, path_class, Severity.MEDIUM, 0.7,
            "max_file_reads", "Agent exceeded the maximum file-read budget.",
        )

    # No violation: task-relevant / adjacent / permitted shared-dependency read.
    if event_type in _MODIFY_EVENTS:
        agg.modifications = True
    return _decision(
        None, path_class, Severity.INFO, 1.0, "in_scope", "In-scope activity.",
    )
