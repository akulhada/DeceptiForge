# Purpose: expose demo-only endpoints that seed data, simulate detection, and return dashboard
#   state. Responsibilities: give the hackathon dashboard a stable, single-fetch data source. These
#   routes are demo scaffolding, not product endpoints. Dependencies: DemoService and the session.
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.dependencies import get_db
from app.repositories.artifacts import ArtifactRepository
from app.schemas.demo import DemoState
from app.services.demo import DemoService

router = APIRouter(prefix="/demo", tags=["demo"])


def _service(session: Session) -> DemoService:
    return DemoService(ArtifactRepository(session))


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
