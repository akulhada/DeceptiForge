# Purpose: run the full DeceptiForge demo pipeline as one deterministic, step-tracked execution.
# Responsibilities: reset demo data, drive scan -> context -> placements -> decoys -> validation ->
#   tripwires -> detection -> alert -> incident -> optional narrative -> coverage, recording each
#   step's status, and expose the run for retrieval and export. In-process only (no job queue).
# Dependencies: the repository, pipeline, demo aggregator, narrative service, and coverage engine.
# FUTURE_HARDENING: durable run storage, background execution, and per-tenant isolation.
from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.config.constants import DEMO_ORGANIZATION_ID
from app.config.settings import Settings
from app.models.domain.decoy import BelievabilityDecision
from app.repositories.artifacts import ArtifactRepository
from app.schemas.demo import DemoRun, DemoRunStatus, DemoRunStep, DemoRunStepStatus
from app.services.coverage import CoverageEngine
from app.services.decoy_generation import DecoyGenerationConfig
from app.services.demo import _FIXTURE_NAME, _FIXTURE_PATH, DemoService
from app.services.incident_narrative import NarrativeService
from app.services.pipeline import PipelineService

_STEPS: tuple[tuple[str, str], ...] = (
    ("repository_analyzed", "Repository analyzed"),
    ("context_built", "Context profile built"),
    ("placements_generated", "Placement recommendations generated"),
    ("decoys_generated", "Decoys generated"),
    ("decoys_validated", "Decoys validated"),
    ("tripwires_armed", "Tripwires armed"),
    ("detection_simulated", "Detection simulated"),
    ("alert_created", "Alert created"),
    ("incident_reconstructed", "Incident reconstructed"),
    ("ai_summary", "AI summary generated or fallback used"),
    ("coverage_calculated", "Coverage calculated"),
)


class RunStore:
    """In-process store of demo runs (demo-only, not durable)."""

    def __init__(self) -> None:
        self._runs: dict[UUID, DemoRun] = {}

    def put(self, run: DemoRun) -> None:
        self._runs[run.run_id] = run

    def get(self, run_id: UUID) -> DemoRun | None:
        return self._runs.get(run_id)

    def clear(self) -> None:
        self._runs.clear()


run_store = RunStore()


class DemoOrchestrator:
    """Runs the end-to-end demo and records each step's status."""

    def __init__(
        self,
        repository: ArtifactRepository,
        settings: Settings,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._repo = repository
        self._settings = settings
        self._pipeline = PipelineService(repository, DEMO_ORGANIZATION_ID)
        self._demo = DemoService(repository)
        self._coverage = CoverageEngine()
        self._clock = clock or (lambda: datetime.now(UTC))

    def reset(self) -> None:
        self._repo.reset_all()
        run_store.clear()

    def run(self) -> DemoRun:
        self.reset()
        steps = {
            key: DemoRunStep(key=key, label=label, status=DemoRunStepStatus.PENDING)
            for key, label in _STEPS
        }

        def mark(key: str, status: DemoRunStepStatus, note: str | None = None) -> None:
            steps[key] = steps[key].model_copy(update={"status": status, "note": note})

        narrative = None
        try:
            mark("repository_analyzed", DemoRunStepStatus.RUNNING)
            repository_id, _ = self._pipeline.scan(str(_FIXTURE_PATH), _FIXTURE_NAME)
            mark("repository_analyzed", DemoRunStepStatus.COMPLETE)

            mark("context_built", DemoRunStepStatus.RUNNING)
            _, _, plan = self._pipeline.plan(repository_id)
            mark("context_built", DemoRunStepStatus.COMPLETE)
            mark(
                "placements_generated",
                DemoRunStepStatus.COMPLETE if plan.recommendations else DemoRunStepStatus.FAILED,
                f"{len(plan.recommendations)} recommendations",
            )

            mark("decoys_generated", DemoRunStepStatus.RUNNING)
            decoy_plan_id, generated = self._pipeline.generate(
                repository_id, DecoyGenerationConfig(namespace=f"demo:{repository_id}")
            )
            mark(
                "decoys_generated",
                DemoRunStepStatus.COMPLETE if generated.assets else DemoRunStepStatus.FAILED,
                f"{len(generated.assets)} decoys",
            )

            mark("decoys_validated", DemoRunStepStatus.RUNNING)
            reports = self._pipeline.evaluate(decoy_plan_id)
            accepted = [r for r in reports if r.decision is BelievabilityDecision.ACCEPT]
            mark(
                "decoys_validated",
                DemoRunStepStatus.COMPLETE,
                f"{len(accepted)}/{len(reports)} accepted",
            )
            mark(
                "tripwires_armed",
                DemoRunStepStatus.COMPLETE if accepted else DemoRunStepStatus.FAILED,
                f"{len(accepted)} armed",
            )

            trace = DemoService._first_accepted_trace(generated, reports)
            mark("detection_simulated", DemoRunStepStatus.RUNNING)
            event, alert = (
                self._pipeline.ingest_event(
                    decoy_plan_id, "repository", "src/exfiltrated.py", f"copied {trace} to laptop"
                )
                if trace is not None
                else (None, None)
            )
            mark(
                "detection_simulated",
                DemoRunStepStatus.COMPLETE if event else DemoRunStepStatus.FAILED,
            )
            mark("alert_created", DemoRunStepStatus.COMPLETE if alert else DemoRunStepStatus.FAILED)

            state = self._demo.state()
            incident = state.incidents[0] if state.incidents else None
            mark(
                "incident_reconstructed",
                DemoRunStepStatus.COMPLETE if incident else DemoRunStepStatus.FAILED,
            )

            if incident is not None:
                narrative = NarrativeService(self._repo, self._settings).generate(
                    DEMO_ORGANIZATION_ID, incident.incident_id
                )
                mark(
                    "ai_summary",
                    DemoRunStepStatus.COMPLETE if narrative else DemoRunStepStatus.FAILED,
                    f"source={narrative.source.value}" if narrative else None,
                )
            else:
                mark("ai_summary", DemoRunStepStatus.FAILED, "no incident")

            coverage = self._coverage.compute(state, narrative_present=narrative is not None)
            mark("coverage_calculated", DemoRunStepStatus.COMPLETE, f"overall={coverage.overall}")
        except Exception as error:  # keep the demo resilient; record and continue
            for key, step in steps.items():
                if step.status is DemoRunStepStatus.RUNNING:
                    mark(key, DemoRunStepStatus.FAILED, type(error).__name__)
            state = self._demo.state()
            coverage = self._coverage.compute(state, narrative_present=narrative is not None)

        overall = (
            DemoRunStatus.FAILED
            if any(step.status is DemoRunStepStatus.FAILED for step in steps.values())
            else DemoRunStatus.COMPLETE
        )
        run = DemoRun(
            run_id=uuid4(),
            created_at=self._clock(),
            status=overall,
            steps=tuple(steps.values()),
            coverage=coverage,
            narrative=narrative,
            state=state,
        )
        run_store.put(run)
        return run

    def get_run(self, run_id: UUID) -> DemoRun | None:
        return run_store.get(run_id)


def render_run_markdown(run: DemoRun) -> str:
    """Render a demo run as a portable Markdown report for the README or a demo video."""
    state = run.state
    lines: list[str] = [
        f"# DeceptiForge demo run `{run.run_id}`",
        "",
        f"- Status: **{run.status.value}**",
        f"- Generated: {run.created_at.isoformat()}",
        "",
        "## Steps",
    ]
    lines += [
        f"- {step.label}: **{step.status.value}**" + (f" — {step.note}" if step.note else "")
        for step in run.steps
    ]

    if state.profile is not None:
        languages = ", ".join(item.name for item in state.profile.languages) or "none"
        frameworks = ", ".join(item.name for item in state.profile.frameworks) or "none"
        lines += [
            "",
            "## Repository",
            f"- Name: {state.profile.repository_name}",
            f"- Files: {state.profile.file_count}",
            f"- Languages: {languages}",
            f"- Frameworks: {frameworks}",
        ]

    if state.placement_plan is not None:
        lines += ["", "## Placements"]
        lines += [
            f"- {rec.target_location} ({rec.target_type}) — priority {rec.placement_priority:.2f}"
            for rec in state.placement_plan.recommendations
        ]

    if state.decoy_plan is not None:
        lines += ["", "## Decoys"]
        lines += [
            f"- {asset.decoy_type} at {asset.target_location} — trace "
            f"{asset.trigger_metadata.trace_identifier}"
            for asset in state.decoy_plan.assets
        ]

    if state.reports:
        lines += ["", "## Validation"]
        lines += [
            f"- {report.decoy_id}: {report.decision} "
            f"(believability {report.overall_believability_score:.0f}, "
            f"safety {report.overall_safety_score:.0f})"
            for report in state.reports
        ]

    if state.alerts:
        alert = state.alerts[0]
        lines += ["", "## Alert", f"- {alert.severity}: {alert.title}"]

    if state.incidents:
        incident = state.incidents[0]
        lines += [
            "",
            "## Incident",
            f"- {incident.severity} {incident.incident_type}: {incident.title}",
            f"- Hypothesis: {incident.root_cause_hypothesis}",
        ]

    if run.narrative is not None:
        lines += [
            "",
            "## AI investigation summary",
            f"- Source: {run.narrative.source.value} (revision {run.narrative.revision_number})",
            f"- {run.narrative.body.executive_summary}",
        ]

    coverage = run.coverage
    lines += [
        "",
        "## Coverage",
        f"- Overall: {coverage.overall:.2f}",
        f"- Repository {coverage.repository:.2f} · Placement {coverage.placement:.2f} · "
        f"Decoy {coverage.decoy_activation:.2f} · Monitoring {coverage.monitoring:.2f} · "
        f"Alerting {coverage.alerting:.2f} · Incident {coverage.incident:.2f} · "
        f"AI {coverage.ai_narrative:.2f}",
    ]
    return "\n".join(lines) + "\n"
