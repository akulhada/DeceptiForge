# Purpose: domain contract for AI-native (RAG / MCP) tripwire deployments and events.
# Responsibilities: define surfaces, the deployment state machine, event types, and immutable models
#   for generated assets, previews, and minimized events. No connector or persistence concerns here.
# Dependencies: the DomainModel base.
from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field

from app.models.domain.base import DomainModel


class SurfaceType(StrEnum):
    RAG_DOCUMENT = "rag_document"
    MCP_RESOURCE = "mcp_resource"
    MCP_CONFIG = "mcp_config"


class AiTripwireStatus(StrEnum):
    DRAFT = "draft"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    DEPLOYING = "deploying"
    DEPLOYED = "deployed"
    DEPLOYED_UNMONITORED = "deployed_unmonitored"
    VERIFICATION_FAILED = "verification_failed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    DRIFT_DETECTED = "drift_detected"
    RETIRING = "retiring"
    RETIRED = "retired"
    EXPIRED = "expired"


class AiEventType(StrEnum):
    # RAG
    DOCUMENT_RETRIEVED = "document_retrieved"
    CHUNK_RETRIEVED = "chunk_retrieved"
    TRACE_IN_MODEL_INPUT = "trace_in_model_input"
    TRACE_IN_ANSWER = "trace_in_answer"
    DOCUMENT_EXPORTED = "document_exported"
    DOCUMENT_COPIED = "document_copied"
    # MCP
    RESOURCE_LISTED = "resource_listed"
    RESOURCE_READ = "resource_read"
    RESOURCE_REFERENCED = "resource_referenced"
    CONFIG_LOADED = "config_loaded"
    URI_REQUESTED = "uri_requested"
    METADATA_COPIED = "metadata_copied"
    AGENT_TOUCHED = "agent_touched"


_RAG_EVENTS = frozenset(
    {
        AiEventType.DOCUMENT_RETRIEVED,
        AiEventType.CHUNK_RETRIEVED,
        AiEventType.TRACE_IN_MODEL_INPUT,
        AiEventType.TRACE_IN_ANSWER,
        AiEventType.DOCUMENT_EXPORTED,
        AiEventType.DOCUMENT_COPIED,
    }
)


def event_surface(event_type: AiEventType) -> SurfaceType:
    return SurfaceType.RAG_DOCUMENT if event_type in _RAG_EVENTS else SurfaceType.MCP_RESOURCE


# Explicit closed state machine. Deployment before validation/approval is blocked in the service
# layer. Illegal transitions are rejected.
_TRANSITIONS: dict[AiTripwireStatus, frozenset[AiTripwireStatus]] = {
    AiTripwireStatus.DRAFT: frozenset(
        {AiTripwireStatus.AWAITING_APPROVAL, AiTripwireStatus.CANCELLED}
    ),
    AiTripwireStatus.AWAITING_APPROVAL: frozenset(
        {AiTripwireStatus.APPROVED, AiTripwireStatus.REJECTED, AiTripwireStatus.CANCELLED}
    ),
    AiTripwireStatus.APPROVED: frozenset(
        {AiTripwireStatus.DEPLOYING, AiTripwireStatus.CANCELLED}
    ),
    AiTripwireStatus.DEPLOYING: frozenset(
        {
            AiTripwireStatus.DEPLOYED,
            AiTripwireStatus.DEPLOYED_UNMONITORED,
            AiTripwireStatus.VERIFICATION_FAILED,
            AiTripwireStatus.FAILED,
        }
    ),
    AiTripwireStatus.DEPLOYED: frozenset(
        {AiTripwireStatus.RETIRING, AiTripwireStatus.DRIFT_DETECTED, AiTripwireStatus.EXPIRED}
    ),
    AiTripwireStatus.DEPLOYED_UNMONITORED: frozenset(
        {AiTripwireStatus.RETIRING, AiTripwireStatus.EXPIRED}
    ),
    AiTripwireStatus.VERIFICATION_FAILED: frozenset({AiTripwireStatus.RETIRING}),
    AiTripwireStatus.FAILED: frozenset(
        {AiTripwireStatus.AWAITING_APPROVAL, AiTripwireStatus.CANCELLED}
    ),
    AiTripwireStatus.DRIFT_DETECTED: frozenset({AiTripwireStatus.RETIRING}),
    AiTripwireStatus.RETIRING: frozenset(
        {AiTripwireStatus.RETIRED, AiTripwireStatus.DRIFT_DETECTED, AiTripwireStatus.FAILED}
    ),
    AiTripwireStatus.EXPIRED: frozenset({AiTripwireStatus.RETIRING}),
    # Terminal states.
    AiTripwireStatus.REJECTED: frozenset(),
    AiTripwireStatus.CANCELLED: frozenset(),
    AiTripwireStatus.RETIRED: frozenset(),
}


class InvalidAiTransitionError(Exception):
    def __init__(self, current: AiTripwireStatus, target: AiTripwireStatus) -> None:
        super().__init__(f"invalid AI tripwire transition: {current.value} -> {target.value}")
        self.current = current
        self.target = target


def can_transition(current: AiTripwireStatus, target: AiTripwireStatus) -> bool:
    return target in _TRANSITIONS.get(current, frozenset())


def assert_transition(current: AiTripwireStatus, target: AiTripwireStatus) -> None:
    if not can_transition(current, target):
        raise InvalidAiTransitionError(current, target)


# ---- generated asset + preview models ------------------------------------------------------------


class GeneratedRagDocument(DomainModel):
    """An inert synthetic RAG document. Multiple trace mechanisms survive chunking/embedding."""

    document_id: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=256)
    body: str = Field(min_length=1, max_length=20_000)
    trace_token: str = Field(min_length=8, max_length=64)
    reserved_phrase: str = Field(min_length=1, max_length=256)
    metadata: dict[str, str]
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class GeneratedMcpResource(DomainModel):
    """An inert synthetic MCP resource/config. No executable tool, no real endpoint."""

    uri: str = Field(min_length=1, max_length=512)
    name: str = Field(min_length=1, max_length=256)
    description: str = Field(min_length=1, max_length=2000)
    mime_type: str = "text/plain"
    trace_token: str = Field(min_length=8, max_length=64)
    metadata: dict[str, str]
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class AiTripwirePreview(DomainModel):
    deployment_id: str
    surface_type: SurfaceType
    connector_id: str
    target_collection: str
    decoy_kind: str
    trace_token: str
    trace_mechanisms: tuple[str, ...]
    exact_content: str
    metadata: dict[str, str]
    safety_ok: bool
    warnings: tuple[str, ...] = ()
    verification_plan: str
    retirement_plan: str
    expires_at: datetime | None
    expected_monitoring_registration: tuple[str, ...]
    preview_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class MinimizedAiEvent(DomainModel):
    """A trusted, minimized AI tripwire event. Never carries prompts/chunks/outputs/embeddings."""

    deployment_id: str
    trace_id: str
    surface_type: SurfaceType
    event_type: AiEventType
    source_id: str = Field(max_length=256)
    monitor_identity: str = Field(max_length=128)
    confidence: float = Field(ge=0, le=1)
    minimized_metadata: dict[str, str]
    observed_at: datetime
