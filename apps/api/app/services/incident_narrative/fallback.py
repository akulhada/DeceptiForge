# Purpose: build a deterministic narrative body without a language model.
# Responsibilities: produce a readable analyst-style summary from incident fields so the feature
#   works with OpenAI absent or failing. Dependencies: the incident and narrative models.
from __future__ import annotations

from app.models.domain.narrative import IncidentNarrativeBody, IncidentNarrativeContext


def fallback_body(context: IncidentNarrativeContext) -> IncidentNarrativeBody:
    """Render a fallback exclusively from the same sanitized context sent to the model."""
    surfaces = ", ".join(context.affected_surfaces) or "monitored surfaces"
    incident_label = context.incident_type.replace("_", " ")
    executive_summary = (
        f"{context.severity.title()}-severity {incident_label} involving "
        f"{context.involved_decoy_count} decoy(s) across {surfaces}. This indicates possible "
        "unauthorized interaction with deception assets, not a confirmed breach."
    )
    analyst_summary = context.root_cause_hypothesis
    if context.correlation_reasons:
        analyst_summary = f"{analyst_summary} {context.correlation_reasons[0]}"

    likely_sequence = tuple(
        f"#{event.sequence} {event.monitor_type}: {event.summary}" for event in context.timeline
    )
    evidence_summary = context.evidence_excerpts
    caveats = (
        ("Generated deterministically without a language model.",)
        + context.false_positive_notes
        + ("Decoy interaction shows possible exposure, not confirmed data loss.",)
    )
    return IncidentNarrativeBody(
        executive_summary=executive_summary,
        analyst_summary=analyst_summary or executive_summary,
        likely_sequence=likely_sequence,
        evidence_summary=evidence_summary,
        recommended_next_actions=context.recommended_actions,
        uncertainty_caveats=caveats,
        confidence_notes=f"Deterministic confidence {context.confidence}.",
    )
