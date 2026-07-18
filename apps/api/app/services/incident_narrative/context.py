# Purpose: build the sanitized, bounded context sent to GPT and hash it.
# Responsibilities: derive a minimized context from a deterministic incident, enforce a token
#   budget by dropping low-priority timeline detail, and compute a stable content hash. It never
#   emits raw payloads. Dependencies: the incident and narrative domain models.
from __future__ import annotations

import hashlib
import json

from app.models.domain.narrative import IncidentNarrativeContext, NarrativeTimelineSummary
from app.models.domain.operations import ReconstructedIncident

_EXCERPT_LIMIT = 120
_SUMMARY_LIMIT = 280
_MAX_TIMELINE = 8
_MAX_EVIDENCE = 5
_TOKEN_BUDGET = 1500
_STANDING_CAVEAT = (
    "Decoy interaction indicates possible unauthorized access, not confirmed data loss."
)


def _clip(text: str, limit: int) -> str:
    return text[:limit]


class NarrativeContextBuilder:
    """Turns an incident into a minimized context under a token budget."""

    def __init__(
        self,
        *,
        token_budget: int = _TOKEN_BUDGET,
        max_timeline: int = _MAX_TIMELINE,
        max_evidence: int = _MAX_EVIDENCE,
    ) -> None:
        self._budget = token_budget
        self._max_timeline = max_timeline
        self._max_evidence = max_evidence

    def build(self, incident: ReconstructedIncident) -> IncidentNarrativeContext:
        timeline = tuple(
            NarrativeTimelineSummary(
                sequence=event.sequence,
                timestamp=event.timestamp,
                monitor_type=event.monitor_type.value,
                summary=_clip(event.summary, _SUMMARY_LIMIT),
                evidence_excerpt=_clip(event.evidence.excerpt, _EXCERPT_LIMIT),
                confidence=event.confidence,
            )
            for event in incident.timeline[: self._max_timeline]
        )
        evidence = incident.evidence_summary[: self._max_evidence]
        context = IncidentNarrativeContext(
            incident_id=incident.incident_id,
            incident_type=incident.incident_type.value,
            severity=incident.severity.value,
            confidence=incident.confidence,
            first_seen=incident.first_seen,
            last_seen=incident.last_seen,
            affected_surfaces=incident.affected_surfaces,
            involved_decoy_count=len(incident.involved_decoy_ids),
            involved_placement_count=len(incident.involved_placement_ids),
            involved_trace_ids=incident.involved_trace_ids,
            timeline=timeline,
            evidence_excerpts=tuple(_clip(item.excerpt, _EXCERPT_LIMIT) for item in evidence),
            evidence_digests=tuple(item.digest for item in evidence),
            root_cause_hypothesis=incident.root_cause_hypothesis,
            recommended_actions=incident.recommended_actions,
            false_positive_notes=incident.false_positive_notes,
            uncertainty_notes=(_STANDING_CAVEAT,),
            correlation_reasons=incident.correlation_reasons,
        )
        return self._apply_budget(context)

    def _apply_budget(self, context: IncidentNarrativeContext) -> IncidentNarrativeContext:
        if self._estimate_tokens(context) <= self._budget:
            return context
        notes: list[str] = []
        # Drop middle timeline detail first; keep the first and last observation.
        if len(context.timeline) > 2:
            notes.append(f"timeline reduced from {len(context.timeline)} to 2 steps")
            context = context.model_copy(
                update={
                    "timeline": (context.timeline[0], context.timeline[-1]),
                    "truncated": True,
                    "truncation_notes": tuple(notes),
                }
            )
        # Then reduce evidence excerpts, preserving severity/type/recommendations/caveats.
        if self._estimate_tokens(context) > self._budget and len(context.evidence_excerpts) > 1:
            notes.append("evidence excerpts reduced to 1")
            context = context.model_copy(
                update={
                    "evidence_excerpts": context.evidence_excerpts[:1],
                    "evidence_digests": context.evidence_digests[:1],
                    "truncated": True,
                    "truncation_notes": tuple(notes),
                }
            )
        return context

    @staticmethod
    def _estimate_tokens(context: IncidentNarrativeContext) -> int:
        # A cheap, dependency-free heuristic (~4 characters per token).
        return len(context.model_dump_json()) // 4


def context_hash(context: IncidentNarrativeContext) -> str:
    """Stable SHA-256 over a canonical serialization of the context."""
    canonical = json.dumps(context.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
