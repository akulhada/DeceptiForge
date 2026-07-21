# Purpose: the AnalysisPreviewResponse contract for the Interactive Demo Lab.
# Responsibilities: express explainable, deterministic analysis output — input summary, inferred
#   context profile, vocabulary, ranked sensitive zones, ranked placement recommendations, layered
#   confidence, and deterministic warnings. Never carries tokens, session data, secrets, server
#   paths, or stack traces. Dependencies: pydantic domain base.
from __future__ import annotations

from datetime import datetime

from pydantic import Field

from app.models.domain.base import DomainModel

# Bump SCHEMA_VERSION on any breaking change to this contract; the frontend surfaces mismatches.
SCHEMA_VERSION = "analysis-preview-v1"
ENGINE_VERSIONS: dict[str, str] = {
    "context_engine": "1.0",
    "placement_reasoning": "1.0",
    "sensitive_zones": "1.0",
    "confidence": "1.0",
}


class InputSummary(DomainModel):
    language_count: int = Field(ge=0)
    framework_count: int = Field(ge=0)
    service_count: int = Field(ge=0)
    database_count: int = Field(ge=0)
    documentation_signal_count: int = Field(ge=0)
    secret_location_count: int = Field(ge=0)
    ai_surface_count: int = Field(ge=0)
    naming_pattern_count: int = Field(ge=0)
    recognized_categories: tuple[str, ...] = ()
    ignored_fields: tuple[str, ...] = ()


class InferredField(DomainModel):
    """A single inferred value with its explanation — never a value without a reason."""

    key: str = Field(min_length=1, max_length=64)
    value: str = Field(max_length=512)
    confidence: float = Field(ge=0, le=1)
    supporting_signals: tuple[str, ...] = Field(default=(), max_length=20)
    reason: str = Field(default="", max_length=512)


class ContextProfileView(DomainModel):
    probable_business_domain: InferredField
    probable_repository_type: InferredField
    dominant_technical_stack: InferredField
    service_architecture: InferredField
    operational_maturity: InferredField
    data_sensitivity: InferredField
    deployment_model: InferredField
    ai_system_exposure: InferredField
    high_value_attacker_interests: tuple[str, ...] = ()


class VocabularyView(DomainModel):
    domain_terms: tuple[str, ...] = ()
    entity_names: tuple[str, ...] = ()
    service_names: tuple[str, ...] = ()
    environment_terms: tuple[str, ...] = ()
    operational_vocabulary: tuple[str, ...] = ()
    prefixes: tuple[str, ...] = ()
    suffixes: tuple[str, ...] = ()
    confidence: float = Field(ge=0, le=1)
    supporting_signals: tuple[str, ...] = Field(default=(), max_length=20)
    # How repository-specific vocabulary influences deception (not generic templates).
    influence_notes: tuple[str, ...] = Field(default=(), max_length=10)


class SensitiveZone(DomainModel):
    zone_id: str = Field(min_length=1, max_length=64)
    category: str = Field(min_length=1, max_length=64)
    representative_paths: tuple[str, ...] = Field(default=(), max_length=20)
    risk_score: float = Field(ge=0, le=1)
    confidence: float = Field(ge=0, le=1)
    supporting_signals: tuple[str, ...] = Field(default=(), max_length=20)
    reasoning: str = Field(default="", max_length=512)
    relevant_decoy_types: tuple[str, ...] = Field(default=(), max_length=10)
    warnings: tuple[str, ...] = Field(default=(), max_length=10)


class PlacementRecommendationView(DomainModel):
    rank: int = Field(ge=1)
    zone: str = Field(min_length=1, max_length=64)
    proposed_path_or_pattern: str = Field(min_length=1, max_length=512)
    decoy_type: str = Field(min_length=1, max_length=64)
    expected_visibility: float = Field(ge=0, le=1)
    business_relevance: float = Field(ge=0, le=1)
    detection_value: float = Field(ge=0, le=1)
    deployment_risk: float = Field(ge=0, le=1)
    confidence: float = Field(ge=0, le=1)
    supporting_signals: tuple[str, ...] = Field(default=(), max_length=20)
    reasoning: str = Field(default="", max_length=512)
    lower_ranked_alternatives: tuple[str, ...] = Field(default=(), max_length=10)


class ConfidenceBreakdown(DomainModel):
    overall: float = Field(ge=0, le=1)
    domain: float = Field(ge=0, le=1)
    vocabulary: float = Field(ge=0, le=1)
    sensitive_zone: float = Field(ge=0, le=1)
    placement: float = Field(ge=0, le=1)
    completeness: float = Field(ge=0, le=1)
    conflict: float = Field(ge=0, le=1)


class AnalysisWarning(DomainModel):
    code: str = Field(min_length=1, max_length=64)
    message: str = Field(min_length=1, max_length=512)
    effect: str = Field(default="", max_length=512)


class AnalysisPreviewResponse(DomainModel):
    schema_version: str
    organization_id: str
    request_id: str
    scenario_id: str | None = None
    input_summary: InputSummary
    context_profile: ContextProfileView
    vocabulary: VocabularyView
    sensitive_zones: tuple[SensitiveZone, ...] = ()
    placement_recommendations: tuple[PlacementRecommendationView, ...] = ()
    warnings: tuple[AnalysisWarning, ...] = ()
    confidence: ConfidenceBreakdown
    engine_versions: dict[str, str]
    generated_at: datetime
    stage_timings_ms: dict[str, float] = Field(default_factory=dict)
