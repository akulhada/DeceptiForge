# Purpose: orchestrate demo-only dataset seeding, detection simulation, and state aggregation.
# Responsibilities: drive the existing PipelineService against a bundled fixture and assemble the
#   single aggregate payload the dashboard renders. It adds no engine or detection logic.
# Dependencies: the artifact repository, the pipeline service, and the bundled fixture.
from __future__ import annotations

from pathlib import Path
from uuid import UUID

from app.config.constants import DEMO_ORGANIZATION_ID
from app.models.domain.decoy import (
    BelievabilityDecision,
    BelievabilitySafetyReport,
    DecoyGenerationPlan,
    DecoyKind,
)
from app.models.domain.intelligence import RepositoryIntelligenceProfile
from app.repositories.artifacts import ArtifactRepository
from app.schemas.demo import DemoCoverage, DemoOverview, DemoState
from app.services.decoy_generation import DecoyGenerationConfig
from app.services.pipeline import PipelineService

_FIXTURE_PATH = Path(__file__).resolve().parent.parent / "demo" / "acme-payments"
_FIXTURE_NAME = "acme-payments"

_COVERAGE_DIMENSIONS: dict[str, frozenset[DecoyKind]] = {
    "repository": frozenset({DecoyKind.SECRET}),
    "database": frozenset({DecoyKind.DATABASE_RECORD}),
    "document": frozenset({DecoyKind.DOCUMENT, DecoyKind.SPREADSHEET_ROW}),
    "ai": frozenset({DecoyKind.MCP_CONFIG, DecoyKind.EMBEDDING, DecoyKind.AGENT_ASSET}),
}


class DemoService:
    """Demo-only façade over the pipeline for a stable, one-call dashboard."""

    def __init__(self, repository: ArtifactRepository) -> None:
        self._repo = repository
        # The demo is a single tenant; it explicitly uses the demo organization (never a silent
        # global default). Production callers pass their authenticated organization instead.
        self._org = DEMO_ORGANIZATION_ID
        self._pipeline = PipelineService(repository, DEMO_ORGANIZATION_ID)

    def seed(self) -> DemoState:
        repository_id, _ = self._pipeline.scan(str(_FIXTURE_PATH), _FIXTURE_NAME)
        self._pipeline.plan(repository_id)
        decoy_plan_id, _ = self._pipeline.generate(
            repository_id, DecoyGenerationConfig(namespace=f"demo:{repository_id}")
        )
        self._pipeline.evaluate(decoy_plan_id)
        return self.state()

    def simulate_detection(self) -> DemoState:
        latest = self._demo_repository()
        if latest is None:
            return self.state()
        repository_id, _ = latest
        decoy = self._repo.latest_decoy_plan(self._org, repository_id)
        if decoy is None:
            return self.state()
        decoy_plan_id, decoy_plan = decoy
        reports = self._repo.reports_for_decoy_plan(self._org, decoy_plan_id)
        trace = self._first_accepted_trace(decoy_plan, reports)
        if trace is not None:
            self._pipeline.ingest_event(
                decoy_plan_id, "repository", "src/exfiltrated.py", f"copied {trace} to laptop"
            )
        return self.state()

    def state(self) -> DemoState:
        latest = self._demo_repository()
        if latest is None:
            return self._empty_state()
        repository_id, profile = latest
        context = self._repo.latest_context(self._org, repository_id)
        placement_plan = self._repo.latest_placement_plan(self._org, repository_id)
        decoy = self._repo.latest_decoy_plan(self._org, repository_id)
        decoy_plan_id = decoy[0] if decoy else None
        decoy_plan = decoy[1] if decoy else None
        reports = (
            self._repo.reports_for_decoy_plan(self._org, decoy_plan_id) if decoy_plan_id else ()
        )
        asset_ids = {asset.decoy_id for asset in decoy_plan.assets} if decoy_plan else set()
        events = self._repo.detection_events_for_decoys(self._org, asset_ids)
        alerts = self._repo.alerts_for_decoys(self._org, asset_ids)
        # Incidents are already organization-scoped; the demo further narrows to the current
        # generation's decoys so a reseed shows a clean story.
        incidents = tuple(
            incident
            for incident in self._repo.incidents_for_organization(self._org)
            if asset_ids.intersection(incident.involved_decoy_ids)
        )
        return DemoState(
            repository_id=repository_id,
            decoy_plan_id=decoy_plan_id,
            profile=profile,
            context=context,
            placement_plan=placement_plan,
            decoy_plan=decoy_plan,
            reports=reports,
            events=events,
            alerts=alerts,
            incidents=incidents,
            overview=self._overview(decoy_plan, reports, len(events), len(alerts), len(incidents)),
        )

    def _demo_repository(self) -> tuple[UUID, RepositoryIntelligenceProfile] | None:
        return self._repo.latest_repository_at_path(self._org, str(_FIXTURE_PATH))

    @staticmethod
    def _first_accepted_trace(
        decoy_plan: DecoyGenerationPlan, reports: tuple[BelievabilitySafetyReport, ...]
    ) -> str | None:
        accepted = {
            report.decoy_id for report in reports if report.decision is BelievabilityDecision.ACCEPT
        }
        for asset in decoy_plan.assets:
            if asset.decoy_id in accepted:
                return asset.trigger_metadata.trace_identifier
        return None

    @staticmethod
    def _overview(
        decoy_plan: DecoyGenerationPlan | None,
        reports: tuple[BelievabilitySafetyReport, ...],
        monitor_events: int,
        alerts: int,
        incidents: int,
    ) -> DemoOverview:
        assets = decoy_plan.assets if decoy_plan else ()
        accepted_ids = {
            report.decoy_id for report in reports if report.decision is BelievabilityDecision.ACCEPT
        }
        accepted_kinds = {asset.decoy_type for asset in assets if asset.decoy_id in accepted_ids}
        total = len(assets)
        accepted = len(accepted_ids)
        coverage = DemoCoverage(
            repository=_covered(accepted_kinds, "repository"),
            database=_covered(accepted_kinds, "database"),
            document=_covered(accepted_kinds, "document"),
            ai=_covered(accepted_kinds, "ai"),
            overall=(accepted / total) if total else 0.0,
        )
        return DemoOverview(
            total_decoys=total,
            accepted_decoys=accepted,
            active_tripwires=accepted,
            monitor_events=monitor_events,
            alerts=alerts,
            incidents=incidents,
            coverage=coverage,
        )

    def _empty_state(self) -> DemoState:
        return DemoState(
            repository_id=None,
            decoy_plan_id=None,
            profile=None,
            context=None,
            placement_plan=None,
            decoy_plan=None,
            reports=(),
            events=(),
            alerts=(),
            incidents=(),
            overview=DemoOverview(
                total_decoys=0,
                accepted_decoys=0,
                active_tripwires=0,
                monitor_events=0,
                alerts=0,
                incidents=0,
                coverage=DemoCoverage(
                    repository=0.0, database=0.0, document=0.0, ai=0.0, overall=0.0
                ),
            ),
        )


def _covered(kinds: set[DecoyKind], dimension: str) -> float:
    return 1.0 if kinds & _COVERAGE_DIMENSIONS[dimension] else 0.0
