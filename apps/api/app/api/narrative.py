# Purpose: expose optional, organization-scoped GPT incident-narrative endpoints.
# Responsibilities: require an organization context, fetch incidents only within that organization,
#   and return/append narrative revisions. It never mutates incident data. Dependencies: the
#   narrative service, repository, settings, and the org auth boundary.
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.config.settings import get_settings
from app.dependencies import get_db
from app.models.domain.narrative import IncidentNarrative
from app.repositories.artifacts import ArtifactRepository
from app.security import OrgContext, require_org
from app.services.incident_narrative import NarrativeService

router = APIRouter(tags=["incidents"])


def _service(session: Session) -> NarrativeService:
    return NarrativeService(ArtifactRepository(session), get_settings())


@router.post("/incidents/{incident_id}/narrative", response_model=IncidentNarrative)
def generate_incident_narrative(
    incident_id: UUID,
    force: bool = False,
    org: OrgContext = Depends(require_org),
    session: Session = Depends(get_db),
) -> IncidentNarrative:
    """Generate or reuse a narrative for an incident owned by the requesting organization."""
    narrative = _service(session).generate(org.organization_id, incident_id, force=force)
    if narrative is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "incident not found")
    return narrative


@router.get("/incidents/{incident_id}/narrative", response_model=IncidentNarrative)
def get_incident_narrative(
    incident_id: UUID,
    org: OrgContext = Depends(require_org),
    session: Session = Depends(get_db),
) -> IncidentNarrative:
    """Return the latest narrative revision for the organization, or 404 if none exists."""
    narrative = _service(session).latest(org.organization_id, incident_id)
    if narrative is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no narrative generated yet")
    return narrative


@router.get("/incidents/{incident_id}/narratives", response_model=list[IncidentNarrative])
def list_incident_narratives(
    incident_id: UUID,
    org: OrgContext = Depends(require_org),
    session: Session = Depends(get_db),
) -> list[IncidentNarrative]:
    """Return all narrative revisions for the incident within the requesting organization."""
    return list(_service(session).history(org.organization_id, incident_id))
