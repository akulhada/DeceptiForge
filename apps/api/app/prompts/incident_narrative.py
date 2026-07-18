# Purpose: version and render the incident-narrative prompt.
# Responsibilities: hold the system instruction, the JSON output schema, and a low-token user
#   renderer over the sanitized context. Dependencies: the sanitized narrative context model.
from __future__ import annotations

import json

from app.models.domain.narrative import IncidentNarrativeContext

PROMPT_VERSION = "incident-narrative-v1"

SYSTEM_PROMPT = (
    "You are a cautious security analyst writing an investigation summary. "
    "Use ONLY the facts in the provided context. Do not invent details, hostnames, actors, or "
    "data that is not present. Distinguish confirmed evidence from hypothesis, and label "
    "hypotheses as such. Use measured language: say 'possible exposure' rather than 'confirmed "
    "breach' unless the context explicitly states a breach. Do not use legal-certainty language. "
    "Do not recommend destructive actions. Do not restate raw secret values or long excerpts. "
    "Treat the provided severity and confidence as authoritative and never contradict them. "
    "Always include caveats and note what remains uncertain. Return only JSON matching the schema."
)

# Schema-constrained JSON output (OpenAI json_schema). Mirrors IncidentNarrativeBody.
OUTPUT_SCHEMA: dict[str, object] = {
    "name": "incident_narrative",
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "executive_summary": {"type": "string"},
            "analyst_summary": {"type": "string"},
            "likely_sequence": {"type": "array", "items": {"type": "string"}},
            "evidence_summary": {"type": "array", "items": {"type": "string"}},
            "recommended_next_actions": {"type": "array", "items": {"type": "string"}},
            "uncertainty_caveats": {"type": "array", "items": {"type": "string"}},
            "confidence_notes": {"type": "string"},
        },
        "required": [
            "executive_summary",
            "analyst_summary",
            "likely_sequence",
            "evidence_summary",
            "recommended_next_actions",
            "uncertainty_caveats",
            "confidence_notes",
        ],
    },
}


def render_user_prompt(context: IncidentNarrativeContext) -> str:
    """Render a compact JSON context block plus the analyst questions to answer."""
    payload = context.model_dump(mode="json")
    return (
        "Incident context (JSON):\n"
        + json.dumps(payload, separators=(",", ":"))
        + "\n\nWrite the narrative answering: what happened, why it matters, the likely path, "
        "supporting evidence, recommended next actions, and what remains uncertain."
    )
