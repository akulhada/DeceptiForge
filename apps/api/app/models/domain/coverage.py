# Purpose: domain contract for the measured deception coverage engine.
# Responsibilities: define surfaces, controls, dimensions, gaps, recommendations, and the versioned
#   methodology enums plus immutable models for a coverage snapshot. Coverage is deterministic and
#   explainable; GPT never scores. No persistence or scoring logic here (see services/coverage).
# Dependencies: the DomainModel base, the shared Severity enum.
from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field

from app.models.domain.base import DomainModel
from app.models.domain.operations import Severity

# Bump when the deterministic formula, weights, or dimension set change. Snapshots record the
# version they were computed under; a version change changes the source_state_hash so historical
# snapshots stay comparable only within a version.
METHODOLOGY_VERSION = "coverage-v1"


class SurfaceType(StrEnum):
    REPOSITORY = "repository"
    DATABASE = "database"
    RAG = "rag"
    MCP = "mcp"
    BROWSER_AI = "browser_ai"
    AI_AGENT = "ai_agent"


class ControlType(StrEnum):
    DECOY = "decoy"
    SENSOR = "sensor"
    MONITORING = "monitoring"
    ALERTING = "alerting"
    INCIDENT_RESPONSE = "incident_response"


class ControlStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    DEGRADED = "degraded"
    EXPIRED = "expired"
    FAILED = "failed"


class CoverageDimension(StrEnum):
    PLACEMENT = "placement"
    SENSOR = "sensor"
    HEALTH = "health"
    ALERTING = "alerting"
    INCIDENT = "incident"
    LIFECYCLE = "lifecycle"
    IDENTITY = "identity"
    CROSS_SURFACE = "cross_surface"
    VERIFICATION = "verification"


class GapType(StrEnum):
    NO_DECOY = "no_decoy"
    DECOY_NO_SENSOR = "decoy_no_sensor"
    SENSOR_UNHEALTHY = "sensor_unhealthy"
    NO_HONEY_RECORDS = "no_honey_records"
    NO_RAG_TRIPWIRE = "no_rag_tripwire"
    NO_MCP_TRIPWIRE = "no_mcp_tripwire"
    SHADOW_AI_NO_POLICY = "shadow_ai_no_policy"
    AGENT_NO_SCOPE_POLICY = "agent_no_scope_policy"
    EXPIRED_NOT_REPLACED = "expired_not_replaced"
    MONITORING_ACTIVATION_FAILED = "monitoring_activation_failed"
    FRAGILE_SINGLE_CONTROL = "fragile_single_control"
    NO_CROSS_SURFACE = "no_cross_surface"


class RecommendedAction(StrEnum):
    ADD_DECOY = "add_decoy"
    ADD_SENSOR = "add_sensor"
    REPLACE_EXPIRED = "replace_expired"
    ADD_BROWSER_POLICY = "add_browser_policy"
    ADD_AGENT_SCOPE_POLICY = "add_agent_scope_policy"
    REPAIR_SENSOR = "repair_sensor"
    DIVERSIFY_CONTROLS = "diversify_controls"


class InventorySurface(DomainModel):
    """One protected surface discovered from the existing integrations. Deterministic scores."""

    surface_type: SurfaceType
    external_or_resource_id: str = Field(max_length=512)
    display_name: str = Field(max_length=256)
    criticality: float = Field(ge=0, le=1)
    exposure_score: float = Field(ge=0, le=1)
    sensitivity_score: float = Field(ge=0, le=1)
    attack_likelihood: float = Field(ge=0, le=1)
    business_impact: float = Field(ge=0, le=1)
    coverage_requirement: float = Field(ge=0, le=1, default=1.0)
    risk_weight: float = Field(ge=0)
    inventory_confidence: float = Field(ge=0, le=1)
    status: str = Field(default="known", max_length=16)
    explanation: str = Field(max_length=512, default="")


class SurfaceControl(DomainModel):
    """A control observed on a surface, with a status and deterministic effectiveness."""

    control_type: ControlType
    control_reference_id: str = Field(max_length=128)
    status: ControlStatus
    effectiveness_score: float = Field(ge=0, le=1)
    confidence: float = Field(ge=0, le=1)
    last_verified_at: datetime | None = None
    dimension: CoverageDimension
    metadata: dict[str, str] = Field(default_factory=dict)


class SurfaceCoverage(DomainModel):
    """The computed, explainable coverage for one surface across all dimensions."""

    surface: InventorySurface
    dimension_scores: dict[CoverageDimension, float]
    surface_coverage: float = Field(ge=0, le=1)
    weighted_coverage: float = Field(ge=0)
    confidence: float = Field(ge=0, le=1)
    is_unknown: bool = False
    control_count: int = 0
    control_diversity: int = 0
    explanation: str = Field(max_length=512, default="")


class CoverageGapModel(DomainModel):
    surface_type: SurfaceType
    external_or_resource_id: str = Field(max_length=512)
    gap_type: GapType
    severity: Severity
    reason: str = Field(max_length=512)
    missing_controls: tuple[str, ...] = ()
    recommended_decoy_type: str | None = None
    recommended_sensor_type: str | None = None
    expected_coverage_gain: float = Field(ge=0, le=1, default=0.0)


class RecommendationModel(DomainModel):
    surface_type: SurfaceType
    external_or_resource_id: str = Field(max_length=512)
    recommended_action: RecommendedAction
    recommended_decoy_type: str | None = None
    target_location: str = Field(max_length=512)
    expected_coverage_gain: float = Field(ge=0, le=1)
    expected_detection_gain: float = Field(ge=0, le=1)
    deployment_risk: float = Field(ge=0, le=1)
    false_positive_risk: float = Field(ge=0, le=1)
    implementation_effort: float = Field(ge=0, le=1)
    priority_score: float = Field(ge=0)
    confidence: float = Field(ge=0, le=1)
    explanation: str = Field(max_length=512)


class CoverageResult(DomainModel):
    """The full deterministic output of one calculation, ready to persist as a snapshot."""

    methodology_version: str
    overall_score: float = Field(ge=0, le=1)
    confidence: float = Field(ge=0, le=1)
    covered_weight: float = Field(ge=0)
    total_weight: float = Field(ge=0)
    unknown_weight: float = Field(ge=0)
    active_decoys: int = 0
    active_sensors: int = 0
    unhealthy_sensors: int = 0
    expired_decoys: int = 0
    blind_spot_count: int = 0
    source_state_hash: str
    surfaces: tuple[SurfaceCoverage, ...] = ()
    gaps: tuple[CoverageGapModel, ...] = ()
    recommendations: tuple[RecommendationModel, ...] = ()


class CoveragePolicyDoc(DomainModel):
    """Versioned, auditable coverage policy. Deterministic weights + thresholds; contains no
    secrets."""

    organization_id: str
    surface_weights: dict[SurfaceType, float] = Field(default_factory=dict)
    dimension_weights: dict[CoverageDimension, float] = Field(default_factory=dict)
    minimum_acceptable_score: float = Field(ge=0, le=1, default=0.6)
    minimum_sensor_health: float = Field(ge=0, le=1, default=0.5)
    verification_freshness_hours: int = 168
    maximum_unknown_weight: float = Field(ge=0, le=1, default=0.4)
    recommendation_risk_tolerance: float = Field(ge=0, le=1, default=0.6)
    policy_version: int = 1
