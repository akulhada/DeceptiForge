# Purpose: domain contract for AI agent activity sensors — sensor identity/state, scoped sessions,
#   deterministic scope policies, minimized activity events, and explainable scope violations.
# Responsibilities: define the sensor + session state machines, event/violation/path-class enums,
#   and immutable models for policy, normalized scope, minimized events, and scope decisions. No
#   persistence, signing, or transport concerns here. Never carries prompts, source, or reasoning.
# Dependencies: the DomainModel base, the shared Severity enum.
from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field

from app.models.domain.base import DomainModel
from app.models.domain.operations import Severity


class AgentSensorStatus(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    DISABLED = "disabled"
    REVOKED = "revoked"


_SENSOR_TRANSITIONS: dict[AgentSensorStatus, frozenset[AgentSensorStatus]] = {
    AgentSensorStatus.PENDING: frozenset({AgentSensorStatus.ACTIVE, AgentSensorStatus.REVOKED}),
    AgentSensorStatus.ACTIVE: frozenset({AgentSensorStatus.DISABLED, AgentSensorStatus.REVOKED}),
    AgentSensorStatus.DISABLED: frozenset({AgentSensorStatus.ACTIVE, AgentSensorStatus.REVOKED}),
    AgentSensorStatus.REVOKED: frozenset(),
}


class InvalidSensorTransitionError(Exception):
    def __init__(self, current: AgentSensorStatus, target: AgentSensorStatus) -> None:
        super().__init__(f"illegal sensor transition {current.value} -> {target.value}")
        self.current = current
        self.target = target


def can_transition(current: AgentSensorStatus, target: AgentSensorStatus) -> bool:
    return target in _SENSOR_TRANSITIONS.get(current, frozenset())


def assert_transition(current: AgentSensorStatus, target: AgentSensorStatus) -> None:
    if not can_transition(current, target):
        raise InvalidSensorTransitionError(current, target)


class AgentSessionStatus(StrEnum):
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class AgentSensorMode(StrEnum):
    """Enforcement mode. Detect-only by default; prevention modes are future and gated."""

    DETECT = "detect"
    WARN = "warn"
    BLOCK = "block"


class AgentEventType(StrEnum):
    SESSION_STARTED = "session_started"
    SESSION_COMPLETED = "session_completed"
    FILE_LISTED = "file_listed"
    FILE_READ = "file_read"
    FILE_MODIFIED = "file_modified"
    FILE_CREATED = "file_created"
    FILE_DELETED = "file_deleted"
    SEARCH_PERFORMED = "search_performed"
    COMMAND_REQUESTED = "command_requested"
    TOOL_INVOKED = "tool_invoked"
    MCP_RESOURCE_LISTED = "mcp_resource_listed"
    MCP_RESOURCE_READ = "mcp_resource_read"
    DATABASE_QUERY_REQUESTED = "database_query_requested"
    NETWORK_REQUEST_REQUESTED = "network_request_requested"
    DECOY_TOUCHED = "decoy_touched"
    SENSITIVE_PATH_ACCESSED = "sensitive_path_accessed"
    DENIED_ACTION_ATTEMPTED = "denied_action_attempted"


_DESTRUCTIVE_EVENTS = frozenset(
    {AgentEventType.FILE_DELETED, AgentEventType.DENIED_ACTION_ATTEMPTED}
)


def is_destructive(event_type: AgentEventType) -> bool:
    return event_type in _DESTRUCTIVE_EVENTS


class ScopeViolationType(StrEnum):
    OUT_OF_SCOPE_PATH_ACCESS = "out_of_scope_path_access"
    SENSITIVE_FILE_ACCESS = "sensitive_file_access"
    DECOY_ASSET_TOUCH = "decoy_asset_touch"
    EXCESSIVE_REPOSITORY_BREADTH = "excessive_repository_breadth"
    UNEXPECTED_DATABASE_ACCESS = "unexpected_database_access"
    UNEXPECTED_NETWORK_ACCESS = "unexpected_network_access"
    UNEXPECTED_MCP_RESOURCE_ACCESS = "unexpected_mcp_resource_access"
    DEPENDENCY_CHANGE_OUTSIDE_SCOPE = "dependency_change_outside_scope"
    REPEATED_SENSITIVE_EXPLORATION = "repeated_sensitive_exploration"
    DESTRUCTIVE_ACTION_ATTEMPT = "destructive_action_attempt"
    CROSS_REPOSITORY_ACCESS = "cross_repository_access"
    UNAPPROVED_TOOL_USE = "unapproved_tool_use"


class PathClass(StrEnum):
    TASK_RELEVANT = "task_relevant"
    ADJACENT = "adjacent"
    SHARED_DEPENDENCY = "shared_dependency"
    SENSITIVE = "sensitive"
    DECOY = "decoy"
    GENERATED = "generated"
    BUILD_OUTPUT = "build_output"
    CREDENTIAL = "credential"
    DEPLOYMENT = "deployment"
    BILLING = "billing"
    AUTHENTICATION = "authentication"
    CUSTOMER_DATA = "customer_data"
    UNRELATED = "unrelated"


# Path classes that are inherently sensitive (elevate severity, count toward sensitive-read caps).
SENSITIVE_CLASSES: frozenset[PathClass] = frozenset(
    {
        PathClass.SENSITIVE,
        PathClass.CREDENTIAL,
        PathClass.DEPLOYMENT,
        PathClass.BILLING,
        PathClass.AUTHENTICATION,
        PathClass.CUSTOMER_DATA,
    }
)


class AgentExposure(StrEnum):
    """Deterministic agent-activity exposure categories for alert/incident classification."""

    AI_AGENT_SCOPE_VIOLATION = "ai_agent_scope_violation"
    AI_AGENT_DECOY_TOUCH = "ai_agent_decoy_touch"
    AI_AGENT_SENSITIVE_EXPLORATION = "ai_agent_sensitive_exploration"
    AI_AGENT_CROSS_SURFACE_EXPOSURE = "ai_agent_cross_surface_exposure"
    AI_AGENT_DESTRUCTIVE_ATTEMPT = "ai_agent_destructive_attempt"
    AI_AGENT_POLICY_VIOLATION = "ai_agent_policy_violation"


class AgentScopePolicyDoc(DomainModel):
    """Bounded, versioned deterministic scope policy. Contains no secrets."""

    organization_id: str
    name: str = Field(max_length=128)
    allowed_paths: tuple[str, ...] = ()
    denied_paths: tuple[str, ...] = ()
    allowed_tools: tuple[str, ...] = ()
    denied_tools: tuple[str, ...] = ()
    allowed_resource_types: tuple[str, ...] = ()
    maximum_file_reads: int = 200
    maximum_sensitive_reads: int = 0
    allow_dependency_changes: bool = False
    allow_secret_file_access: bool = False
    allow_database_access: bool = False
    allow_network_access: bool = False
    policy_version: int = 1


class MinimizedAgentEvent(DomainModel):
    """A trusted, minimized agent activity event. Never carries file content, command output,
    prompts, or model reasoning."""

    external_event_id: str = Field(min_length=1, max_length=128)  # idempotency key
    session_id: str
    event_type: AgentEventType
    normalized_path: str | None = Field(default=None, max_length=2048)
    tool_name: str | None = Field(default=None, max_length=128)
    resource_type: str | None = Field(default=None, max_length=64)
    resource_id_hash: str | None = Field(default=None, max_length=128)
    trace_id: str | None = Field(default=None, max_length=128)
    result_status: str = Field(default="ok", max_length=32)
    minimized_metadata: dict[str, str] = Field(default_factory=dict)
    observed_at: datetime


class ScopeDecision(DomainModel):
    """Deterministic, explainable outcome of scoring one event against a session's scope."""

    violation_type: ScopeViolationType | None
    path_class: PathClass
    severity: Severity
    confidence: float = Field(ge=0, le=1)
    policy_rule: str = Field(max_length=128)
    explanation: str = Field(max_length=512)
    decoy_id: str | None = None
