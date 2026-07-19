# Purpose: domain contract for browser AI-paste sensors — sensor identity/state, organization AI
#   policy, the compact trace registry, and minimized browser paste events.
# Responsibilities: define the sensor state machine, destination/exposure classifications, event
#   types, and immutable models for policy, registry entries, and minimized events. No persistence,
#   signing, or transport concerns here. Never carries pasted text or conversation content.
# Dependencies: the DomainModel base.
from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field

from app.models.domain.base import DomainModel


class SensorStatus(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    REVOKED = "revoked"
    DISABLED = "disabled"


# Closed sensor state machine. Revoked is terminal (a revoked credential can never report again).
_SENSOR_TRANSITIONS: dict[SensorStatus, frozenset[SensorStatus]] = {
    SensorStatus.PENDING: frozenset({SensorStatus.ACTIVE, SensorStatus.REVOKED}),
    SensorStatus.ACTIVE: frozenset(
        {SensorStatus.DISABLED, SensorStatus.REVOKED}
    ),
    SensorStatus.DISABLED: frozenset({SensorStatus.ACTIVE, SensorStatus.REVOKED}),
    SensorStatus.REVOKED: frozenset(),
}


class InvalidSensorTransitionError(Exception):
    def __init__(self, current: SensorStatus, target: SensorStatus) -> None:
        super().__init__(f"illegal sensor transition {current.value} -> {target.value}")
        self.current = current
        self.target = target


def can_transition(current: SensorStatus, target: SensorStatus) -> bool:
    return target in _SENSOR_TRANSITIONS.get(current, frozenset())


def assert_transition(current: SensorStatus, target: SensorStatus) -> None:
    if not can_transition(current, target):
        raise InvalidSensorTransitionError(current, target)


class DestinationClass(StrEnum):
    """How a destination AI domain is classified by organization policy."""

    APPROVED = "approved"
    CONDITIONAL = "conditional"
    SHADOW = "shadow"
    UNKNOWN = "unknown"
    IGNORED = "ignored"


class TraceMatchMode(StrEnum):
    EXACT = "exact"
    NORMALIZED = "normalized"


class MatchMethod(StrEnum):
    EXACT = "exact"
    NORMALIZED = "normalized"
    FINGERPRINT = "fingerprint"


class BrowserEventType(StrEnum):
    AI_PASTE_TRACE_DETECTED = "ai_paste_trace_detected"
    SHADOW_AI_PASTE_DETECTED = "shadow_ai_paste_detected"
    APPROVED_AI_PASTE_DETECTED = "approved_ai_paste_detected"
    REPEATED_AI_PASTE = "repeated_ai_paste"
    MULTI_TOOL_AI_EXPOSURE = "multi_tool_ai_exposure"
    EXTENSION_POLICY_VIOLATION = "extension_policy_violation"
    BROWSER_SENSOR_DISABLED = "browser_sensor_disabled"
    TRACE_REGISTRY_STALE = "trace_registry_stale"


class BrowserAiExposure(StrEnum):
    """Deterministic AI-paste exposure categories for alert/incident classification."""

    AI_PASTE_LEAK = "ai_paste_leak"
    SHADOW_AI_EXPOSURE = "shadow_ai_exposure"
    APPROVED_AI_POLICY_VIOLATION = "approved_ai_policy_violation"
    REPEATED_CROSS_TOOL_PASTE = "repeated_cross_tool_paste"
    MULTI_SURFACE_AI_EXPOSURE = "multi_surface_ai_exposure"


class DomainRule(DomainModel):
    """One policy entry: a destination domain and its classification. No account identity."""

    domain: str = Field(min_length=1, max_length=253)
    classification: DestinationClass
    label: str | None = Field(default=None, max_length=64)


class BrowserAiPolicyDoc(DomainModel):
    """Versioned organization policy delivered to sensors. Bounded; contains no secrets."""

    organization_id: str
    enabled: bool
    monitored_domains: tuple[str, ...]
    rules: tuple[DomainRule, ...]
    trace_match_mode: TraceMatchMode
    local_only_mode: bool
    event_reporting_enabled: bool
    show_user_notification: bool
    allow_pause: bool
    min_extension_version: str
    policy_version: int
    updated_at: datetime
    # Optional detached signature over the canonical policy body (hex). Present when the deployment
    # requires signed policies; the extension rejects a policy whose version regresses.
    signature: str | None = None


class TraceRegistryEntry(DomainModel):
    """A compact, irreversible trace fingerprint. Never a full decoy document or real secret."""

    trace_id: str = Field(min_length=1, max_length=128)
    # Irreversible lookup token (hash of the marker). The extension matches against this; the raw
    # marker value is never shipped.
    match_token: str = Field(min_length=1, max_length=128)
    match_mode: TraceMatchMode
    decoy_category: str | None = Field(default=None, max_length=64)
    status: str = Field(max_length=16)
    expires_at: datetime | None = None


class TraceRegistryDoc(DomainModel):
    """Bounded, organization-scoped registry snapshot delivered to a sensor."""

    organization_id: str
    policy_version: int
    entries: tuple[TraceRegistryEntry, ...]
    generated_at: datetime


class MinimizedBrowserEvent(DomainModel):
    """A trusted, minimized browser paste event. Never carries pasted text or conversation."""

    browser_sensor_id: str
    trace_id: str = Field(min_length=1, max_length=128)
    destination_domain: str = Field(min_length=1, max_length=253)
    destination_classification: DestinationClass
    event_type: BrowserEventType
    match_method: MatchMethod
    confidence: float = Field(ge=0, le=1)
    extension_version: str = Field(max_length=32)
    policy_version: int
    # Optional irreversible hash of a local excerpt — never the excerpt itself.
    excerpt_hash: str | None = Field(default=None, max_length=128)
    minimized_metadata: dict[str, str] = Field(default_factory=dict)
    observed_at: datetime
