# Purpose: domain contracts for the controlled learning + calibration engine.
# Responsibilities: define the VERSIONED normalized feature schema (categories, buckets, scores and
#   hashes only — never source content, secrets, customer records, prompts, or model output), the
#   immutable learning-event taxonomy, outcome/feedback enumerations, the model-version state
#   machine, and the recommendation change explanation.
# Dependencies: pydantic domain base. No I/O.
from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import Field

from app.models.domain.base import DomainModel

# Bump when the normalized feature contract changes; snapshots and model versions are pinned to it
# so an incompatible candidate can never be promoted onto a different schema.
FEATURE_SCHEMA_VERSION = "features-v1"
METHODOLOGY_VERSION = "calibration-v1"

MAX_CATEGORY = 64
MAX_CATEGORIES = 20
MAX_REASON_CODES = 20


class Bucket(StrEnum):
    """Coarse magnitude buckets — deliberately lossy so counts cannot re-identify a tenant."""

    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    VERY_HIGH = "very_high"


def bucket_of(count: int) -> Bucket:
    """Deterministic bucketing for any raw count. Never store the raw count."""
    if count <= 0:
        return Bucket.NONE
    if count <= 2:
        return Bucket.LOW
    if count <= 5:
        return Bucket.MEDIUM
    if count <= 15:
        return Bucket.HIGH
    return Bucket.VERY_HIGH


class NormalizedFeatures(DomainModel):
    """The ONLY shape learning may consume. Categories/buckets/scores — no raw content.

    Every field is either a bounded enumeration, a coarse bucket, or a 0..1 score. There is no
    free-text field and no path field by design: a reviewer can verify minimization by reading this
    contract alone.
    """

    dominant_language_category: str = Field(default="unknown", max_length=MAX_CATEGORY)
    framework_categories: tuple[str, ...] = Field(default=(), max_length=MAX_CATEGORIES)
    repository_architecture: str = Field(default="unknown", max_length=MAX_CATEGORY)
    business_domain_category: str = Field(default="unknown", max_length=MAX_CATEGORY)
    service_count_bucket: Bucket = Bucket.NONE
    documentation_density_bucket: Bucket = Bucket.NONE
    ai_surface_count_bucket: Bucket = Bucket.NONE
    deployment_complexity_bucket: Bucket = Bucket.NONE
    sensitive_zone_categories: tuple[str, ...] = Field(default=(), max_length=MAX_CATEGORIES)
    secrets_exposure_score: float = Field(default=0.0, ge=0, le=1)
    naming_consistency_score: float = Field(default=0.0, ge=0, le=1)
    profile_confidence: float = Field(default=0.0, ge=0, le=1)
    signal_conflict_score: float = Field(default=0.0, ge=0, le=1)


class LearningSourceType(StrEnum):
    REPOSITORY_SIGNALS = "repository_signals"
    ANALYSIS_PREVIEW = "analysis_preview"
    PLACEMENT_PLAN = "placement_plan"


class OutcomeType(StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    DEPLOYED = "deployed"
    DEPLOYMENT_FAILED = "deployment_failed"
    TRIGGERED = "triggered"
    NOT_TRIGGERED = "not_triggered"
    ROLLED_BACK = "rolled_back"
    RETIRED = "retired"
    EXPIRED = "expired"


# Outcomes that may lower a placement's effectiveness score. DEPLOYMENT_FAILED and ROLLED_BACK are
# deliberately absent: those are operational failures, not evidence the placement was wrong.
NEGATIVE_EFFECTIVENESS_OUTCOMES: frozenset[OutcomeType] = frozenset(
    {OutcomeType.REJECTED, OutcomeType.NOT_TRIGGERED}
)
POSITIVE_EFFECTIVENESS_OUTCOMES: frozenset[OutcomeType] = frozenset(
    {OutcomeType.ACCEPTED, OutcomeType.DEPLOYED, OutcomeType.TRIGGERED}
)
OPERATIONAL_OUTCOMES: frozenset[OutcomeType] = frozenset(
    {OutcomeType.DEPLOYMENT_FAILED, OutcomeType.ROLLED_BACK}
)


class FeedbackType(StrEnum):
    FALSE_POSITIVE = "false_positive"
    CONFIRMED_INCIDENT = "confirmed_incident"
    SEVERITY_TOO_HIGH = "severity_too_high"
    SEVERITY_TOO_LOW = "severity_too_low"
    PLACEMENT_USEFUL = "placement_useful"
    PLACEMENT_NOT_USEFUL = "placement_not_useful"
    REASONING_CORRECT = "reasoning_correct"
    REASONING_INCOMPLETE = "reasoning_incomplete"
    REASONING_INCORRECT = "reasoning_incorrect"


class LearningEventType(StrEnum):
    FEATURE_SNAPSHOT_CAPTURED = "feature_snapshot_captured"
    RECOMMENDATION_RECORDED = "recommendation_recorded"
    OUTCOME_RECORDED = "outcome_recorded"
    ANALYST_FEEDBACK_SUBMITTED = "analyst_feedback_submitted"
    OPERATIONAL_RESULT_RECORDED = "operational_result_recorded"


class ModelScope(StrEnum):
    GLOBAL = "global"
    ORGANIZATION = "organization"


class ModelStatus(StrEnum):
    CANDIDATE = "candidate"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    ACTIVE = "active"
    REJECTED = "rejected"
    ROLLED_BACK = "rolled_back"
    ARCHIVED = "archived"


# The only permitted transitions. candidate->active and rejected->active are absent by design.
ALLOWED_TRANSITIONS: dict[ModelStatus, frozenset[ModelStatus]] = {
    ModelStatus.CANDIDATE: frozenset({ModelStatus.UNDER_REVIEW, ModelStatus.REJECTED}),
    ModelStatus.UNDER_REVIEW: frozenset({ModelStatus.APPROVED, ModelStatus.REJECTED}),
    ModelStatus.APPROVED: frozenset({ModelStatus.ACTIVE, ModelStatus.REJECTED}),
    ModelStatus.ACTIVE: frozenset({ModelStatus.ROLLED_BACK, ModelStatus.ARCHIVED}),
    ModelStatus.REJECTED: frozenset({ModelStatus.ARCHIVED}),
    ModelStatus.ROLLED_BACK: frozenset({ModelStatus.ARCHIVED, ModelStatus.ACTIVE}),
    ModelStatus.ARCHIVED: frozenset(),
}


def transition_allowed(current: ModelStatus, target: ModelStatus) -> bool:
    return target in ALLOWED_TRANSITIONS.get(current, frozenset())


class CalibrationWeights(DomainModel):
    """What calibration is permitted to change — confidence/ranking/priors only.

    Safety rules (protected paths, rejection rules, authorization, approval, secret handling,
    deployment boundaries) are NOT represented here and therefore cannot be altered by calibration.
    """

    zone_priors: dict[str, float] = Field(default_factory=dict)
    decoy_type_priors: dict[str, float] = Field(default_factory=dict)
    confidence_scale: float = Field(default=1.0, ge=0.5, le=1.5)
    evidence_strength: float = Field(default=1.0, ge=0.5, le=1.5)
    tie_breaker: str = Field(default="deterministic", max_length=32)


class CohortMetric(DomainModel):
    """A measured rate with its uncertainty — never false precision on a small sample."""

    cohort: str = Field(min_length=1, max_length=128)
    sample_count: int = Field(ge=0)
    successes: int = Field(ge=0)
    rate: float = Field(ge=0, le=1)
    wilson_low: float = Field(ge=0, le=1)
    wilson_high: float = Field(ge=0, le=1)
    distinct_actors: int = Field(default=0, ge=0)
    sufficient: bool = False


class CalibrationMetrics(DomainModel):
    acceptance: tuple[CohortMetric, ...] = ()
    trigger: tuple[CohortMetric, ...] = ()
    false_positive: tuple[CohortMetric, ...] = ()
    confidence_calibration_error: float = Field(default=0.0, ge=0, le=1)
    included_event_count: int = Field(default=0, ge=0)
    excluded_event_count: int = Field(default=0, ge=0)
    exclusion_reasons: dict[str, int] = Field(default_factory=dict)


class RecommendationChangeExplanation(DomainModel):
    """Structured 'why this changed' — never implies causality beyond the sample."""

    previous_model_version: UUID | None = None
    active_model_version: UUID | None = None
    changed: bool = False
    changed_factors: tuple[str, ...] = Field(default=(), max_length=10)
    previous_confidence: float | None = None
    current_confidence: float | None = None
    previous_rank: int | None = None
    current_rank: int | None = None
    sample_count: int = Field(default=0, ge=0)
    confidence_interval: tuple[float, float] | None = None
    organization_specific: bool = False
    global_aggregate_used: bool = False
    explanation: str = Field(default="", max_length=512)


class OperationType(StrEnum):
    ANALYSIS = "analysis"
    EVENT_INGESTION = "event_ingestion"
    ALERT_CREATION = "alert_creation"
    INCIDENT_RECONSTRUCTION = "incident_reconstruction"
    DEPLOYMENT = "deployment"
    MONITORING_ACTIVATION = "monitoring_activation"


class AttributionDecision(DomainModel):
    """Whether an outcome may be used as effectiveness evidence, and why not when excluded."""

    usable: bool
    reason_code: str = Field(default="", max_length=64)
    observation_hours: float = Field(default=0.0, ge=0)
    healthy_monitoring_ratio: float = Field(default=0.0, ge=0, le=1)


class CalibrationReport(DomainModel):
    """Explainable candidate report shown at review time."""

    methodology_version: str
    feature_schema_version: str
    training_window_start: datetime
    training_window_end: datetime
    included_event_count: int = Field(ge=0)
    excluded_event_count: int = Field(ge=0)
    exclusion_reasons: dict[str, int] = Field(default_factory=dict)
    previous_weights: CalibrationWeights | None = None
    candidate_weights: CalibrationWeights
    metrics: CalibrationMetrics
    safety_constraints_preserved: bool = True
    known_limitations: tuple[str, ...] = Field(default=(), max_length=10)
