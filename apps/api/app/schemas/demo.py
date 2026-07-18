# Purpose: define demo-only aggregate response contracts for the dashboard.
# Responsibilities: bundle every pipeline artifact plus derived overview metrics into one payload so
#   the dashboard renders from a single fetch. Dependencies: domain models for embedded results.
from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel

from app.models.domain.decoy import BelievabilitySafetyReport, DecoyGenerationPlan
from app.models.domain.intelligence import (
    OrganizationContextProfile,
    PlacementPlan,
    RepositoryIntelligenceProfile,
)
from app.models.domain.narrative import IncidentNarrative
from app.models.domain.operations import (
    NormalizedAlert,
    RawDetectionEvent,
    ReconstructedIncident,
)


class DemoCoverage(BaseModel):
    """Presentation-only coverage estimate derived from generated decoys (not a security metric)."""

    repository: float
    database: float
    document: float
    ai: float
    overall: float


class DemoOverview(BaseModel):
    total_decoys: int
    accepted_decoys: int
    active_tripwires: int
    monitor_events: int
    alerts: int
    incidents: int
    coverage: DemoCoverage


class DemoState(BaseModel):
    """Everything the dashboard needs, in one response."""

    repository_id: UUID | None
    decoy_plan_id: UUID | None
    profile: RepositoryIntelligenceProfile | None
    context: OrganizationContextProfile | None
    placement_plan: PlacementPlan | None
    decoy_plan: DecoyGenerationPlan | None
    reports: tuple[BelievabilitySafetyReport, ...]
    events: tuple[RawDetectionEvent, ...]
    alerts: tuple[NormalizedAlert, ...]
    incidents: tuple[ReconstructedIncident, ...]
    overview: DemoOverview


class CoverageSummary(BaseModel):
    """Lightweight, weighted deception-coverage estimate for the demo dashboard.

    Not enterprise coverage analytics; each dimension is a 0..1 signal and overall is their
    weighted average.
    """

    repository: float
    placement: float
    decoy_activation: float
    monitoring: float
    alerting: float
    incident: float
    ai_narrative: float
    overall: float


class DemoRunStepStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"


class DemoRunStep(BaseModel):
    key: str
    label: str
    status: DemoRunStepStatus
    note: str | None = None


class DemoRunStatus(StrEnum):
    COMPLETE = "complete"
    FAILED = "failed"


class DemoRun(BaseModel):
    """One end-to-end demo execution: ordered step statuses plus the resulting artifacts."""

    run_id: UUID
    created_at: datetime
    status: DemoRunStatus
    steps: tuple[DemoRunStep, ...]
    coverage: CoverageSummary
    narrative: IncidentNarrative | None
    state: DemoState
