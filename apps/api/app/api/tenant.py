# Purpose: authenticated, organization-scoped read endpoints for the tenant dashboard.
# Responsibilities: expose a connection check and organization-scoped lists so a production-like
#   UI can load real data without the demo routes. Dependencies: repository, auth, session.
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.dependencies import get_db
from app.models.domain.intelligence import RepositoryIntelligenceProfile
from app.models.domain.operations import RawDetectionEvent
from app.repositories.artifacts import ArtifactRepository
from app.security import current_auth, require_scope
from app.services.api_keys import AuthContext

router = APIRouter(tags=["tenant"])


class WhoAmIResponse(BaseModel):
    organization_id: UUID
    role: str
    scopes: tuple[str, ...]


class RepositorySummary(BaseModel):
    repository_id: UUID
    name: str
    profile: RepositoryIntelligenceProfile


class RepositoryListResponse(BaseModel):
    repositories: tuple[RepositorySummary, ...]


class MonitoringEventListResponse(BaseModel):
    events: tuple[RawDetectionEvent, ...]


@router.get("/whoami", response_model=WhoAmIResponse)
def whoami(auth: AuthContext = Depends(current_auth)) -> WhoAmIResponse:
    return WhoAmIResponse(
        organization_id=auth.organization_id, role=auth.role, scopes=tuple(sorted(auth.scopes))
    )


@router.get("/repositories", response_model=RepositoryListResponse)
def list_repositories(
    auth: AuthContext = Depends(require_scope("repositories:read")),
    session: Session = Depends(get_db),
) -> RepositoryListResponse:
    rows = ArtifactRepository(session).repositories_for_organization(auth.organization_id)
    return RepositoryListResponse(
        repositories=tuple(
            RepositorySummary(repository_id=rid, name=name, profile=profile)
            for rid, name, profile in rows
        )
    )


@router.get("/monitoring/events", response_model=MonitoringEventListResponse)
def list_monitoring_events(
    auth: AuthContext = Depends(require_scope("monitoring:read")),
    session: Session = Depends(get_db),
) -> MonitoringEventListResponse:
    events = ArtifactRepository(session).detection_events_for_organization(auth.organization_id)
    return MonitoringEventListResponse(events=events)
