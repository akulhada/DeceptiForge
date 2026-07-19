# Purpose: verify browser-sensor pure services — minimization, deterministic classification/
#   severity, destination classification, and irreversible trace fingerprints.
from __future__ import annotations

from app.models.domain.browser_sensor import (
    BrowserAiExposure,
    BrowserEventType,
    DestinationClass,
    DomainRule,
    TraceMatchMode,
)
from app.models.domain.operations import Severity
from app.services.browser_sensor.classification import classify, severity
from app.services.browser_sensor.minimize import minimize_metadata, serialize_metadata
from app.services.browser_sensor.policy import classify_destination
from app.services.browser_sensor.registry import fingerprint


def test_minimize_drops_raw_content() -> None:
    out = minimize_metadata(
        {
            "field_count": 2,
            "pasted_text": "SECRET PROMPT",  # forbidden
            "excerpt": "raw excerpt",  # forbidden
            "conversation": "history",  # forbidden
            "note": "x" * 500,  # oversized -> dropped
            "editor": "contenteditable",
        }
    )
    assert "pasted_text" not in out and "excerpt" not in out and "conversation" not in out
    assert "note" not in out
    assert out["editor"] == "contenteditable"
    ser = serialize_metadata(out)
    assert "SECRET PROMPT" not in ser and "raw excerpt" not in ser


def test_classification_is_deterministic() -> None:
    ev = BrowserEventType
    dc = DestinationClass
    a = classify(ev.SHADOW_AI_PASTE_DETECTED, dc.SHADOW, distinct_tools=1)
    b = classify(ev.SHADOW_AI_PASTE_DETECTED, dc.SHADOW, distinct_tools=1)
    assert a == b == BrowserAiExposure.SHADOW_AI_EXPOSURE
    assert (
        classify(ev.APPROVED_AI_PASTE_DETECTED, dc.APPROVED, distinct_tools=1)
        == BrowserAiExposure.AI_PASTE_LEAK
    )
    assert (
        classify(ev.AI_PASTE_TRACE_DETECTED, dc.APPROVED, distinct_tools=2)
        == BrowserAiExposure.MULTI_SURFACE_AI_EXPOSURE
    )


def test_severity_bumps_deterministically() -> None:
    base = severity(
        BrowserAiExposure.AI_PASTE_LEAK, event_count=1, distinct_tools=1, cross_surface=False
    )
    bumped = severity(
        BrowserAiExposure.AI_PASTE_LEAK, event_count=5, distinct_tools=2, cross_surface=True
    )
    order = (Severity.INFO, Severity.LOW, Severity.MEDIUM, Severity.HIGH, Severity.CRITICAL)
    assert base == Severity.MEDIUM
    assert order.index(bumped) > order.index(base)
    assert bumped == severity(
        BrowserAiExposure.AI_PASTE_LEAK, event_count=5, distinct_tools=2, cross_surface=True
    )


def test_classify_destination_longest_match_wins() -> None:
    rules = (
        DomainRule(domain="chatgpt.com", classification=DestinationClass.SHADOW),
        DomainRule(domain="tenant.chatgpt.com", classification=DestinationClass.APPROVED),
    )
    assert classify_destination("tenant.chatgpt.com", rules)[0] == DestinationClass.APPROVED
    assert classify_destination("chatgpt.com", rules)[0] == DestinationClass.SHADOW
    assert classify_destination("unknown.ai", rules)[0] == DestinationClass.UNKNOWN


def test_fingerprint_is_irreversible_and_normalizable() -> None:
    token = fingerprint("DFAI-abc123", TraceMatchMode.EXACT)
    assert token != "DFAI-abc123"  # hashed, not the raw marker
    assert len(token) == 64
    # Normalized mode collapses case.
    assert fingerprint("DFAI-ABC", TraceMatchMode.NORMALIZED) == fingerprint(
        "dfai-abc", TraceMatchMode.NORMALIZED
    )
    assert fingerprint("DFAI-ABC", TraceMatchMode.EXACT) != fingerprint(
        "dfai-abc", TraceMatchMode.EXACT
    )
