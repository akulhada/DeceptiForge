# Purpose: bounded, deterministic session sequence analysis.
# Responsibilities: over a bounded window of recent path classes, detect escalation from adjacent to
#   sensitive/decoy access and probing-after-denied patterns, and produce a deterministic session
#   summary. No O(n^2) full-history scan. Pure.
from __future__ import annotations

from app.models.domain.agent_sensor import SENSITIVE_CLASSES, PathClass

_WINDOW = 20


def detect_escalation(recent_path_classes: list[PathClass]) -> bool:
    """True when unrelated/adjacent probing is followed by sensitive or decoy access within the
    bounded window (escalation), which is more suspicious than isolated sensitive reads."""
    window = recent_path_classes[-_WINDOW:]
    probed = False
    for cls in window:
        if cls in (PathClass.UNRELATED, PathClass.ADJACENT):
            probed = True
        elif probed and (cls in SENSITIVE_CLASSES or cls == PathClass.DECOY):
            return True
    return False


def session_summary(
    *,
    event_count: int,
    violation_count: int,
    distinct_unrelated: int,
    sensitive_reads: int,
    surfaces: frozenset[str],
    decoy_touched: bool,
    escalation: bool,
    modifications: bool,
) -> dict[str, str]:
    """A deterministic, bounded, content-free session summary for the incident record."""
    return {
        "events": str(event_count),
        "violations": str(violation_count),
        "unrelated_paths": str(distinct_unrelated),
        "sensitive_reads": str(sensitive_reads),
        "surfaces": ",".join(sorted(surfaces)) or "none",
        "decoy_touched": "yes" if decoy_touched else "no",
        "escalation": "yes" if escalation else "no",
        "modifications": "yes" if modifications else "no",
    }
