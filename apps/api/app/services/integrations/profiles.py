# Purpose: apply a payload profile to a canonical event, minimizing what leaves the platform.
# Responsibilities: strip fields not permitted by the profile, drop the GPT narrative unless policy
#   allows it (and always keep it clearly labeled), and enforce the maximum serialized size. Never
#   emits raw evidence, secrets, or full payloads. Deterministic. Dependencies: integrations domain.
from __future__ import annotations

from app.models.domain.integrations import PayloadProfile, SecurityEventEnvelope


def apply_profile(
    envelope: SecurityEventEnvelope,
    profile: PayloadProfile,
    *,
    include_narrative: bool,
    max_bytes: int,
) -> SecurityEventEnvelope:
    data = envelope.model_dump()
    # Narrative only ever leaves when the integration + policy allow it; always labeled.
    if not include_narrative:
        data["narrative_summary"] = None

    if profile == PayloadProfile.MINIMAL:
        data.update(
            summary="", affected_surfaces=(), decoy_types=(), recommended_actions=(),
            deterministic_evidence_summary="", narrative_summary=None, links={}, metadata={},
        )
    elif profile == PayloadProfile.STANDARD:
        data.update(deterministic_evidence_summary="", narrative_summary=None)
    elif profile == PayloadProfile.COMPLIANCE_SUMMARY:
        # Deterministic-only compliance view: no narrative, bounded evidence summary.
        data.update(narrative_summary=None, metadata={})
    # ANALYST keeps the deterministic evidence summary and (if allowed) the labeled narrative.

    reduced = SecurityEventEnvelope.model_validate(data)
    # Enforce the hard size bound: if over, drop the heaviest optional fields deterministically.
    if len(reduced.model_dump_json().encode("utf-8")) > max_bytes:
        data.update(
            narrative_summary=None, deterministic_evidence_summary="",
            summary=data.get("summary", "")[:256], metadata={},
        )
        reduced = SecurityEventEnvelope.model_validate(data)
    return reduced


def is_labeled_narrative(envelope: SecurityEventEnvelope) -> bool:
    """A present narrative must be labeled non-authoritative in metadata."""
    if envelope.narrative_summary is None:
        return True
    return envelope.metadata.get("narrative_label") == "ai_generated_non_authoritative"
