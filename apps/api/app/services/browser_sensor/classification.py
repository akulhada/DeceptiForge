# Purpose: deterministically classify browser AI-paste exposure and severity.
# Responsibilities: map an event type + destination classification to an exposure category, and
#   assign severity from category, destination, repetition, multiple tools, and cross-surface
#   correlation. Fully deterministic — GPT never assigns severity. Dependencies: browser domain,
#   the shared Severity enum.
from __future__ import annotations

from app.models.domain.browser_sensor import (
    BrowserAiExposure,
    BrowserEventType,
    DestinationClass,
)
from app.models.domain.operations import Severity


def classify(
    event_type: BrowserEventType, destination: DestinationClass, *, distinct_tools: int
) -> BrowserAiExposure:
    """Deterministically classify one alert's exposure category."""
    if distinct_tools >= 2:
        return BrowserAiExposure.MULTI_SURFACE_AI_EXPOSURE
    if event_type == BrowserEventType.MULTI_TOOL_AI_EXPOSURE:
        return BrowserAiExposure.MULTI_SURFACE_AI_EXPOSURE
    if event_type == BrowserEventType.REPEATED_AI_PASTE:
        return BrowserAiExposure.REPEATED_CROSS_TOOL_PASTE
    if destination in (DestinationClass.SHADOW, DestinationClass.UNKNOWN):
        return BrowserAiExposure.SHADOW_AI_EXPOSURE
    if destination == DestinationClass.CONDITIONAL:
        return BrowserAiExposure.APPROVED_AI_POLICY_VIOLATION
    # Approved destination: still a decoy leaving into an AI tool.
    return BrowserAiExposure.AI_PASTE_LEAK


_BASE_SEVERITY: dict[BrowserAiExposure, Severity] = {
    BrowserAiExposure.AI_PASTE_LEAK: Severity.MEDIUM,
    BrowserAiExposure.APPROVED_AI_POLICY_VIOLATION: Severity.MEDIUM,
    BrowserAiExposure.SHADOW_AI_EXPOSURE: Severity.HIGH,
    BrowserAiExposure.REPEATED_CROSS_TOOL_PASTE: Severity.HIGH,
    BrowserAiExposure.MULTI_SURFACE_AI_EXPOSURE: Severity.CRITICAL,
}

_ORDER = (Severity.INFO, Severity.LOW, Severity.MEDIUM, Severity.HIGH, Severity.CRITICAL)


def severity(
    exposure: BrowserAiExposure,
    *,
    event_count: int,
    distinct_tools: int,
    cross_surface: bool,
) -> Severity:
    """Deterministic severity: base, bumped for repetition, multiple tools, or cross-surface
    correlation (same trace also seen in RAG/MCP/repo/db)."""
    level = _ORDER.index(_BASE_SEVERITY[exposure])
    level += int(event_count >= 3)
    level += int(distinct_tools >= 2)
    level += int(cross_surface)
    return _ORDER[min(level, len(_ORDER) - 1)]
