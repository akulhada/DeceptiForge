# Purpose: define demo-only aggregate response contracts for the dashboard.
# Responsibilities: bundle every pipeline artifact plus derived overview metrics into one payload so
#   the dashboard renders from a single fetch. Dependencies: domain models for embedded results.
from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel

from app.models.domain.decoy import BelievabilitySafetyReport, DecoyGenerationPlan
from app.models.domain.intelligence import (
    OrganizationContextProfile,
    PlacementPlan,
    RepositoryIntelligenceProfile,
)
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
