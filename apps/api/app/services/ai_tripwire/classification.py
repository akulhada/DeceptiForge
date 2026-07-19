# Purpose: deterministically classify AI-native exposure and severity from tripwire events.
# Responsibilities: map event types to an AI exposure category and assign severity from category,
#   repetition, distinct sources, and multiple surfaces. Fully deterministic — GPT never assigns
#   severity. Dependencies: AI event types, the shared Severity enum.
from __future__ import annotations

from enum import StrEnum

from app.models.domain.ai_tripwire import AiEventType, SurfaceType, event_surface
from app.models.domain.operations import Severity


class AiExposureType(StrEnum):
    RAG_RETRIEVAL_EXPOSURE = "rag_retrieval_exposure"
    RAG_ANSWER_LEAK = "rag_answer_leak"
    MCP_RESOURCE_ACCESS = "mcp_resource_access"
    MCP_CONFIG_EXPOSURE = "mcp_config_exposure"
    AI_AGENT_DECOY_TOUCH = "ai_agent_decoy_touch"
    MULTI_SURFACE_AI_EXPOSURE = "multi_surface_ai_exposure"


_SINGLE: dict[AiEventType, AiExposureType] = {
    AiEventType.DOCUMENT_RETRIEVED: AiExposureType.RAG_RETRIEVAL_EXPOSURE,
    AiEventType.CHUNK_RETRIEVED: AiExposureType.RAG_RETRIEVAL_EXPOSURE,
    AiEventType.TRACE_IN_MODEL_INPUT: AiExposureType.RAG_RETRIEVAL_EXPOSURE,
    AiEventType.TRACE_IN_ANSWER: AiExposureType.RAG_ANSWER_LEAK,
    AiEventType.DOCUMENT_EXPORTED: AiExposureType.RAG_RETRIEVAL_EXPOSURE,
    AiEventType.DOCUMENT_COPIED: AiExposureType.RAG_RETRIEVAL_EXPOSURE,
    AiEventType.RESOURCE_LISTED: AiExposureType.MCP_RESOURCE_ACCESS,
    AiEventType.RESOURCE_READ: AiExposureType.MCP_RESOURCE_ACCESS,
    AiEventType.RESOURCE_REFERENCED: AiExposureType.MCP_RESOURCE_ACCESS,
    AiEventType.URI_REQUESTED: AiExposureType.MCP_RESOURCE_ACCESS,
    AiEventType.METADATA_COPIED: AiExposureType.MCP_RESOURCE_ACCESS,
    AiEventType.CONFIG_LOADED: AiExposureType.MCP_CONFIG_EXPOSURE,
    AiEventType.AGENT_TOUCHED: AiExposureType.AI_AGENT_DECOY_TOUCH,
}

_BASE_SEVERITY: dict[AiExposureType, Severity] = {
    AiExposureType.RAG_RETRIEVAL_EXPOSURE: Severity.MEDIUM,
    AiExposureType.RAG_ANSWER_LEAK: Severity.HIGH,
    AiExposureType.MCP_RESOURCE_ACCESS: Severity.MEDIUM,
    AiExposureType.MCP_CONFIG_EXPOSURE: Severity.HIGH,
    AiExposureType.AI_AGENT_DECOY_TOUCH: Severity.HIGH,
    AiExposureType.MULTI_SURFACE_AI_EXPOSURE: Severity.CRITICAL,
}

_ORDER = (Severity.INFO, Severity.LOW, Severity.MEDIUM, Severity.HIGH, Severity.CRITICAL)


def classify(event_types: frozenset[AiEventType]) -> AiExposureType:
    """Deterministically classify one alert's exposure category from its event types."""
    surfaces = {event_surface(e) for e in event_types}
    if len(surfaces) > 1:
        return AiExposureType.MULTI_SURFACE_AI_EXPOSURE
    # Answer leak (trace appeared in a generated answer) dominates retrieval within RAG.
    if AiEventType.TRACE_IN_ANSWER in event_types:
        return AiExposureType.RAG_ANSWER_LEAK
    if AiEventType.CONFIG_LOADED in event_types and surfaces == {SurfaceType.MCP_RESOURCE}:
        return AiExposureType.MCP_CONFIG_EXPOSURE
    if AiEventType.AGENT_TOUCHED in event_types:
        return AiExposureType.AI_AGENT_DECOY_TOUCH
    # Otherwise the most common single mapping.
    return _SINGLE[next(iter(event_types))]


def severity(
    exposure: AiExposureType, *, event_count: int, distinct_sources: int, surface_count: int
) -> Severity:
    """Deterministic severity: base, bumped for repetition, sources, or surfaces."""
    level = _ORDER.index(_BASE_SEVERITY[exposure])
    level += int(event_count >= 3)
    level += int(distinct_sources >= 2)
    level += int(surface_count >= 2)
    return _ORDER[min(level, len(_ORDER) - 1)]
