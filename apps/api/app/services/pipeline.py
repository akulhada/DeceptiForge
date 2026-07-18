# Purpose: orchestrate the deception pipeline as reusable use cases over persistence.
# Responsibilities: chain the existing engines (scan, context, placement, generation,
#   believability, monitoring, alerting, incidents) and persist each artifact. It adds no
#   detection logic of its own; engines remain the single source of truth.
# Dependencies: the artifact repository and the deterministic engines.
from __future__ import annotations

from pathlib import Path
from uuid import UUID

from app.models.domain.decoy import BelievabilitySafetyReport, DecoyGenerationPlan
from app.models.domain.intelligence import (
    PlacementPlan,
    PlacementRecommendation,
    RepositoryIntelligenceProfile,
)
from app.models.domain.operations import (
    NormalizedAlert,
    RawDetectionEvent,
    ReconstructedIncident,
)
from app.repositories.artifacts import ArtifactRepository
from app.services.alerting import AlertingPipeline
from app.services.believability import BelievabilitySafetyEngine
from app.services.context_engine import ContextEngine
from app.services.decoy_generation import DecoyGenerationPlanner
from app.services.incident_reconstruction import IncidentReconstructionEngine
from app.services.monitoring import MonitoringInstrumentationEngine
from app.services.placement_reasoning import PlacementReasoningEngine
from app.services.repository_intelligence import LocalRepositoryScanner


class PipelineError(Exception):
    """Raised when a use case is invoked against a missing prerequisite artifact."""


class PipelineService:
    """Coordinates engines and persistence for the API vertical slice."""

    def __init__(
        self,
        repository: ArtifactRepository,
        *,
        scanner: LocalRepositoryScanner | None = None,
        context_engine: ContextEngine | None = None,
        placement_engine: PlacementReasoningEngine | None = None,
        decoy_planner: DecoyGenerationPlanner | None = None,
        believability_engine: BelievabilitySafetyEngine | None = None,
        incident_engine: IncidentReconstructionEngine | None = None,
    ) -> None:
        self._repo = repository
        self._scanner = scanner or LocalRepositoryScanner()
        self._context = context_engine or ContextEngine()
        self._placement = placement_engine or PlacementReasoningEngine()
        self._decoys = decoy_planner or DecoyGenerationPlanner()
        self._believability = believability_engine or BelievabilitySafetyEngine()
        self._incidents = incident_engine or IncidentReconstructionEngine()

    def scan(self, path: str, name: str | None) -> tuple[UUID, RepositoryIntelligenceProfile]:
        profile = self._scanner.scan(Path(path))
        repository_id = self._repo.add_repository(name or profile.repository_name, path, profile)
        return repository_id, profile

    def get_profile(self, repository_id: UUID) -> RepositoryIntelligenceProfile | None:
        return self._repo.get_profile(repository_id)

    def plan(self, repository_id: UUID) -> tuple[UUID, UUID, PlacementPlan]:
        profile = self._require_profile(repository_id)
        context = self._context.build(profile)
        context_id = self._repo.add_context(repository_id, context)
        plan = self._placement.plan(profile, context)
        plan_id = self._repo.add_placement_plan(repository_id, plan)
        return plan_id, context_id, plan

    def generate(self, repository_id: UUID) -> tuple[UUID, DecoyGenerationPlan]:
        profile = self._require_profile(repository_id)
        context = self._repo.latest_context(repository_id)
        plan = self._repo.latest_placement_plan(repository_id)
        if context is None or plan is None:
            raise PipelineError("placement plan must be created before generating decoys")
        generated = self._decoys.generate(profile, context, plan)
        decoy_plan_id = self._repo.add_decoy_plan(repository_id, generated)
        return decoy_plan_id, generated

    def evaluate(self, decoy_plan_id: UUID) -> tuple[BelievabilitySafetyReport, ...]:
        loaded = self._repo.get_decoy_plan(decoy_plan_id)
        if loaded is None:
            raise PipelineError(f"decoy plan {decoy_plan_id} not found")
        repository_id, decoy_plan = loaded
        profile = self._require_profile(repository_id)
        context = self._repo.latest_context(repository_id)
        placement_plan = self._repo.latest_placement_plan(repository_id)
        if context is None or placement_plan is None:
            raise PipelineError("context and placement plan are required to evaluate decoys")
        recommendations = self._recommendation_by_location(placement_plan)
        reports: list[BelievabilitySafetyReport] = []
        for asset in decoy_plan.assets:
            recommendation = recommendations.get(asset.target_location)
            if recommendation is None:
                continue
            report = self._believability.evaluate(asset, context, profile, recommendation)
            self._repo.add_validation_report(decoy_plan_id, report)
            reports.append(report)
        return tuple(reports)

    def ingest_event(
        self, decoy_plan_id: UUID, surface: str, location: str, value: str
    ) -> tuple[RawDetectionEvent | None, NormalizedAlert | None]:
        loaded = self._repo.get_decoy_plan(decoy_plan_id)
        if loaded is None:
            raise PipelineError(f"decoy plan {decoy_plan_id} not found")
        _, decoy_plan = loaded
        reports = self._repo.reports_for_decoy_plan(decoy_plan_id)
        monitor = MonitoringInstrumentationEngine()
        monitor.register(decoy_plan.assets, reports)
        event = self._scan_surface(monitor, surface, location, value)
        if event is None:
            return None, None
        self._repo.add_detection_event(event)
        alert = AlertingPipeline().ingest(event, None)
        if alert is not None:
            self._repo.add_alert(alert)
            self._repo.replace_incidents(self._incidents.reconstruct(self._repo.all_alerts()))
        return event, alert

    def alerts(self) -> tuple[NormalizedAlert, ...]:
        return self._repo.all_alerts()

    def incidents(self) -> tuple[ReconstructedIncident, ...]:
        return self._repo.all_incidents()

    def _require_profile(self, repository_id: UUID) -> RepositoryIntelligenceProfile:
        profile = self._repo.get_profile(repository_id)
        if profile is None:
            raise PipelineError(f"repository {repository_id} has no stored profile")
        return profile

    @staticmethod
    def _scan_surface(
        monitor: MonitoringInstrumentationEngine, surface: str, location: str, value: str
    ) -> RawDetectionEvent | None:
        if surface == "file":
            return monitor.scan_file_content(location, value)
        if surface == "repository":
            return monitor.scan_repository_file(location, value)
        if surface == "database":
            return monitor.scan_database_payload(location, value)
        if surface == "text":
            return monitor.scan_text(value, location)
        raise PipelineError(f"unknown monitoring surface: {surface}")

    @staticmethod
    def _recommendation_by_location(plan: PlacementPlan) -> dict[str, PlacementRecommendation]:
        return {rec.target_location: rec for rec in plan.recommendations}
