# Purpose: build a deterministic narrative body without a language model.
# Responsibilities: produce a readable analyst-style summary from incident fields so the feature
#   works with OpenAI absent or failing. Dependencies: the incident and narrative models.
from __future__ import annotations

from app.models.domain.narrative import IncidentNarrativeBody
from app.models.domain.operations import ReconstructedIncident

_EXCERPT_LIMIT = 120


def fallback_body(incident: ReconstructedIncident) -> IncidentNarrativeBody:
    surfaces = ", ".join(incident.affected_surfaces) or "monitored surfaces"
    incident_label = incident.incident_type.value.replace("_", " ")
    executive_summary = (
        f"{incident.severity.value.title()}-severity {incident_label} involving "
        f"{len(incident.involved_decoy_ids)} decoy(s) across {surfaces}. This indicates possible "
        "unauthorized interaction with deception assets, not a confirmed breach."
    )
    analyst_summary = incident.root_cause_hypothesis
    if incident.correlation_reasons:
        analyst_summary = f"{analyst_summary} {incident.correlation_reasons[0]}"

    likely_sequence = tuple(
        f"#{event.sequence} {event.monitor_type.value}: {event.summary}"
        for event in incident.timeline
    )
    evidence_summary = tuple(
        f"{item.location}: {item.excerpt[:_EXCERPT_LIMIT]}"
        for item in incident.evidence_summary[:5]
    )
    caveats = (
        ("Generated deterministically without a language model.",)
        + incident.false_positive_notes
        + ("Decoy interaction shows possible exposure, not confirmed data loss.",)
    )
    return IncidentNarrativeBody(
        executive_summary=executive_summary,
        analyst_summary=analyst_summary or executive_summary,
        likely_sequence=likely_sequence,
        evidence_summary=evidence_summary,
        recommended_next_actions=incident.recommended_actions,
        uncertainty_caveats=caveats,
        confidence_notes=f"Deterministic confidence {incident.confidence}.",
    )
