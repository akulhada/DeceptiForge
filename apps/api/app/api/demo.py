# Purpose: expose demo-only endpoints that seed data, run the full demo, and return dashboard state.
# Responsibilities: give the hackathon dashboard a stable data source and one-click orchestration.
#   These routes are demo scaffolding, mounted only when DEMO_ENABLED is true. Dependencies: the
#   demo and orchestrator services and the session.
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.config.settings import get_settings
from app.dependencies import get_db
from app.repositories.artifacts import ArtifactRepository
from app.schemas.demo import DemoRun, DemoState
from app.services.demo import DemoService
from app.services.demo_orchestrator import DemoOrchestrator, render_run_markdown

router = APIRouter(prefix="/demo", tags=["demo"])


def _service(session: Session) -> DemoService:
    return DemoService(ArtifactRepository(session))


def _orchestrator(session: Session) -> DemoOrchestrator:
    return DemoOrchestrator(ArtifactRepository(session), get_settings())


@router.get("/state", response_model=DemoState)
def get_demo_state(session: Session = Depends(get_db)) -> DemoState:
    """Return the full pipeline state for the dashboard in one payload."""
    return _service(session).state()


@router.post("/seed", response_model=DemoState)
def seed_demo(session: Session = Depends(get_db)) -> DemoState:
    """Scan the bundled fixture and run the whole pipeline, returning the seeded state."""
    return _service(session).seed()


@router.post("/simulate-detection", response_model=DemoState)
def simulate_detection(session: Session = Depends(get_db)) -> DemoState:
    """Simulate an accepted decoy being touched, producing an event, alert, and incident."""
    return _service(session).simulate_detection()


@router.post("/reset", response_model=DemoState)
def reset_demo(session: Session = Depends(get_db)) -> DemoState:
    """Delete all demo artifacts and return the empty state."""
    _orchestrator(session).reset()
    return _service(session).state()


@router.post("/run", response_model=DemoRun)
def run_demo(session: Session = Depends(get_db)) -> DemoRun:
    """Run the full end-to-end demo and return the step-tracked result."""
    return _orchestrator(session).run()


@router.get("/run/{run_id}", response_model=DemoRun)
def get_demo_run(run_id: UUID, session: Session = Depends(get_db)) -> DemoRun:
    """Return a previously executed demo run."""
    run = _orchestrator(session).get_run(run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "demo run not found")
    return run


@router.get("/run/{run_id}/export")
def export_demo_run(
    run_id: UUID, format: str = "json", session: Session = Depends(get_db)
) -> Response:
    """Export a demo run as JSON or Markdown for the README or a demo video."""
    run = _orchestrator(session).get_run(run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "demo run not found")
    if format == "markdown":
        return Response(content=render_run_markdown(run), media_type="text/markdown")
    return Response(content=run.model_dump_json(), media_type="application/json")
