# Purpose: define the sanitized incident-narrative contracts.
# Responsibilities: model the minimized context sent to GPT, the model-fillable narrative body, and
#   the stored narrative envelope. These never carry raw payloads and never override deterministic
#   incident fields. Dependencies: the domain base and operational enums.
from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import Field

from app.models.domain.base import DomainModel


class NarrativeSource(StrEnum):
    """Where the narrative text came from."""

    MODEL = "model"
    FALLBACK = "fallback"


class NarrativeStatus(StrEnum):
    """Outcome of a narrative request; fallbacks record why the model was not used."""

    GENERATED = "generated"
    FALLBACK_DISABLED = "fallback_disabled"
    FALLBACK_ERROR = "fallback_error"
    FALLBACK_INVALID = "fallback_invalid"


class TokenUsage(DomainModel):
    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)
    total_tokens: int = Field(ge=0)


class NarrativeTimelineSummary(DomainModel):
    """One minimized timeline step: no raw payloads, only a short summary and bounded excerpt."""

    sequence: int = Field(ge=1)
    timestamp: datetime
    monitor_type: str = Field(min_length=1, max_length=64)
    summary: str = Field(min_length=1, max_length=280)
    evidence_excerpt: str = Field(max_length=120)
    confidence: float = Field(ge=0, le=1)


class IncidentNarrativeContext(DomainModel):
    """The only data sent to GPT. Derived from the deterministic incident, minimized and bounded."""

    incident_id: UUID
    incident_type: str
    severity: str
    confidence: float = Field(ge=0, le=1)
    first_seen: datetime
    last_seen: datetime
    affected_surfaces: tuple[str, ...] = ()
    involved_decoy_count: int = Field(ge=0)
    involved_placement_count: int = Field(ge=0)
    involved_trace_ids: tuple[str, ...] = ()
    timeline: tuple[NarrativeTimelineSummary, ...] = ()
    evidence_excerpts: tuple[str, ...] = ()
    evidence_digests: tuple[str, ...] = ()
    root_cause_hypothesis: str
    recommended_actions: tuple[str, ...] = ()
    false_positive_notes: tuple[str, ...] = ()
    uncertainty_notes: tuple[str, ...] = ()
    correlation_reasons: tuple[str, ...] = ()
    truncated: bool = False
    truncation_notes: tuple[str, ...] = ()


class IncidentNarrativeBody(DomainModel):
    """The model-fillable (or fallback-filled) narrative. Never a source of truth for severity."""

    executive_summary: str = Field(min_length=1, max_length=2000)
    analyst_summary: str = Field(min_length=1, max_length=4000)
    likely_sequence: tuple[str, ...] = Field(default=(), max_length=20)
    evidence_summary: tuple[str, ...] = Field(default=(), max_length=20)
    recommended_next_actions: tuple[str, ...] = Field(default=(), max_length=20)
    uncertainty_caveats: tuple[str, ...] = Field(default=(), max_length=20)
    confidence_notes: str = Field(default="", max_length=1000)


class IncidentNarrative(DomainModel):
    """Stored narrative envelope; sits beside, never replaces, the deterministic incident."""

    narrative_id: UUID
    incident_id: UUID
    organization_id: UUID
    revision_number: int = Field(default=1, ge=1)
    source: NarrativeSource
    status: NarrativeStatus
    model: str | None = None
    prompt_version: str
    source_context_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    created_at: datetime
    body: IncidentNarrativeBody
    token_usage: TokenUsage | None = None
    error: str | None = Field(default=None, max_length=1000)
    schema_version: int = Field(default=1, ge=1)
