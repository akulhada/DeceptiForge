# Purpose: expose the curated demo story — seed data, run the fixed narrative, return its state.
# Responsibilities: give the demo a stable data source and one-click orchestration, and require a
#   scoped credential wherever these routes are hosted. Mounted only when DEMO_ENABLED is true AND
#   the environment permits the demo surface (development or judge).
# Security: five of these routes MUTATE. In a hosted judge environment they are internet-reachable,
#   so they require a `demo:run` credential bound to the demo organization. Development keeps them
#   open for local convenience, the same way the demo API key bypass is development-only.
# Dependencies: the demo and orchestrator services, settings, security, and the session.
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.config.constants import DEMO_ORGANIZATION_ID
from app.config.settings import Settings, get_settings
from app.dependencies import get_db
from app.repositories.artifacts import ArtifactRepository
from app.schemas.demo import DemoRun, DemoState
from app.security import require_scope
from app.services.api_keys import AuthContext
from app.services.demo import DemoService
from app.services.demo_orchestrator import DemoOrchestrator, render_run_markdown

router = APIRouter(prefix="/demo", tags=["demo"])


def demo_access(
    request: Request,
    x_deceptiforge_org_id: str | None = Header(default=None),
    x_deceptiforge_api_key: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
    session: Session = Depends(get_db),
) -> None:
    """Authorize a demo request.

    Development runs the demo unauthenticated for local convenience. Anywhere the demo can be
    hosted — which today means the judge environment — a `demo:run` credential is required, and it
    must be bound to the demo organization: these routes only ever touch that organization, so a
    credential for any other one is refused rather than silently operating on demo data.
    """
    if settings.is_development:
        return None
    context: AuthContext = require_scope("demo:run")(
        request=request,
        x_deceptiforge_org_id=x_deceptiforge_org_id,
        x_deceptiforge_api_key=x_deceptiforge_api_key,
        settings=settings,
        session=session,
    )
    if context.organization_id != DEMO_ORGANIZATION_ID:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "this credential is not bound to the demo organization",
        )
    return None


def _service(session: Session) -> DemoService:
    return DemoService(ArtifactRepository(session))


def _orchestrator(session: Session) -> DemoOrchestrator:
    return DemoOrchestrator(ArtifactRepository(session), get_settings())


@router.get("/state", response_model=DemoState, dependencies=[Depends(demo_access)])
def get_demo_state(session: Session = Depends(get_db)) -> DemoState:
    """Return the full pipeline state for the dashboard in one payload."""
    return _service(session).state()


@router.get("/status", response_model=DemoState, dependencies=[Depends(demo_access)])
def get_demo_status(session: Session = Depends(get_db)) -> DemoState:
    """Compatibility status view for deterministic demo progress; never exposes credentials."""
    return _service(session).state()


@router.post("/seed", response_model=DemoState, dependencies=[Depends(demo_access)])
def seed_demo(session: Session = Depends(get_db)) -> DemoState:
    """Scan the bundled fixture and run the whole pipeline, returning the seeded state."""
    return _service(session).seed()


@router.post("/simulate-detection", response_model=DemoState, dependencies=[Depends(demo_access)])
def simulate_detection(session: Session = Depends(get_db)) -> DemoState:
    """Simulate an accepted decoy being touched, producing an event, alert, and incident."""
    return _service(session).simulate_detection()


@router.post("/trigger", response_model=DemoState, dependencies=[Depends(demo_access)])
def trigger_demo(session: Session = Depends(get_db)) -> DemoState:
    """Development-only controlled touch; the normal pipeline creates event, alert, and incident."""
    return _service(session).simulate_detection()


@router.post("/reset", response_model=DemoState, dependencies=[Depends(demo_access)])
def reset_demo(session: Session = Depends(get_db)) -> DemoState:
    """Delete all demo artifacts and return the empty state."""
    _orchestrator(session).reset()
    return _service(session).state()


@router.post("/run", response_model=DemoRun, dependencies=[Depends(demo_access)])
def run_demo(session: Session = Depends(get_db)) -> DemoRun:
    """Run the full end-to-end demo and return the step-tracked result."""
    return _orchestrator(session).run()


@router.get("/run/{run_id}", response_model=DemoRun, dependencies=[Depends(demo_access)])
def get_demo_run(run_id: UUID, session: Session = Depends(get_db)) -> DemoRun:
    """Return a previously executed demo run."""
    run = _orchestrator(session).get_run(run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "demo run not found")
    return run


@router.get("/run/{run_id}/export", dependencies=[Depends(demo_access)])
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
