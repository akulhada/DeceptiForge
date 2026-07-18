# Purpose: expose optional GPT incident-narrative endpoints.
# Responsibilities: generate a narrative on demand from a stored deterministic incident and return
#   a previously generated one. It never mutates incident data and always returns a narrative
#   (fallback when GPT is unavailable). Dependencies: the generator, repository, and settings.
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.config.settings import get_settings
from app.dependencies import get_db
from app.models.domain.narrative import IncidentNarrative
from app.repositories.artifacts import ArtifactRepository
from app.services.incident_narrative import IncidentNarrativeGenerator

router = APIRouter(tags=["incidents"])


@router.post("/incidents/{incident_id}/narrative", response_model=IncidentNarrative)
def generate_incident_narrative(
    incident_id: UUID, session: Session = Depends(get_db)
) -> IncidentNarrative:
    """Generate (or regenerate) a narrative for a stored incident and persist it."""
    repository = ArtifactRepository(session)
    incident = repository.get_incident(incident_id)
    if incident is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "incident not found")
    narrative = IncidentNarrativeGenerator(get_settings()).generate(incident)
    repository.upsert_narrative(narrative)
    return narrative


@router.get("/incidents/{incident_id}/narrative", response_model=IncidentNarrative)
def get_incident_narrative(
    incident_id: UUID, session: Session = Depends(get_db)
) -> IncidentNarrative:
    """Return a previously generated narrative, or 404 if none exists yet."""
    narrative = ArtifactRepository(session).get_narrative(incident_id)
    if narrative is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no narrative generated yet")
    return narrative
