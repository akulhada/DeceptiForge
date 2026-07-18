# Purpose: define request and response contracts for the pipeline API.
# Responsibilities: keep transport payloads explicit and separate from domain models, which are
#   embedded as immutable result bodies. Dependencies: domain models for response composition.
from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.domain.decoy import BelievabilitySafetyReport, DecoyGenerationPlan
from app.models.domain.intelligence import PlacementPlan, RepositoryIntelligenceProfile
from app.models.domain.operations import (
    NormalizedAlert,
    RawDetectionEvent,
    ReconstructedIncident,
)

MonitoringSurface = Literal["file", "repository", "database", "text"]


class ScanRequest(BaseModel):
    path: str = Field(min_length=1, max_length=4096)
    name: str | None = Field(default=None, max_length=256)


class RepositoryRef(BaseModel):
    repository_id: UUID


class DecoyPlanRef(BaseModel):
    decoy_plan_id: UUID


class MonitoringEventRequest(BaseModel):
    decoy_plan_id: UUID
    surface: MonitoringSurface
    location: str = Field(min_length=1, max_length=2048)
    # A generous character bound; the endpoint enforces the exact byte limit and returns 413.
    value: str = Field(min_length=1, max_length=1_000_000)


class ScanResponse(BaseModel):
    repository_id: UUID
    profile: RepositoryIntelligenceProfile


class PlacementPlanResponse(BaseModel):
    placement_plan_id: UUID
    context_profile_id: UUID
    plan: PlacementPlan


class DecoyPlanResponse(BaseModel):
    decoy_plan_id: UUID
    plan: DecoyGenerationPlan


class ValidationResponse(BaseModel):
    decoy_plan_id: UUID
    reports: tuple[BelievabilitySafetyReport, ...]


class MonitoringEventResponse(BaseModel):
    detected: bool
    event: RawDetectionEvent | None
    alert: NormalizedAlert | None


class AlertListResponse(BaseModel):
    alerts: tuple[NormalizedAlert, ...]


class IncidentListResponse(BaseModel):
    incidents: tuple[ReconstructedIncident, ...]
