# Purpose: expose the deception pipeline over HTTP.
# Responsibilities: translate requests into PipelineService use cases and map missing prerequisites
#   to HTTP errors. It holds no business logic. Dependencies: the service, repository, and schemas.
from __future__ import annotations

from collections.abc import Callable
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.config.settings import get_settings
from app.dependencies import get_db
from app.models.domain.intelligence import RepositoryIntelligenceProfile
from app.repositories.artifacts import ArtifactRepository, ArtifactTooLargeError
from app.schemas.api import (
    AlertListResponse,
    DecoyPlanRef,
    DecoyPlanResponse,
    IncidentListResponse,
    MonitoringEventRequest,
    MonitoringEventResponse,
    PlacementPlanResponse,
    RepositoryRef,
    ScanRequest,
    ScanResponse,
    ValidationResponse,
)
from app.security import OrgContext, require_org
from app.services.pipeline import PipelineError, PipelineService
from app.services.rate_limit import rate_limiter

router = APIRouter()


def _service(session: Session, org: OrgContext) -> PipelineService:
    repository = ArtifactRepository(session, get_settings().max_artifact_bytes)
    return PipelineService(repository, org.organization_id)


@router.post("/repositories/scan", response_model=ScanResponse, tags=["repositories"])
def scan_repository(
    body: ScanRequest,
    org: OrgContext = Depends(require_org),
    session: Session = Depends(get_db),
) -> ScanResponse:
    # Scanning a caller-supplied server path is only acceptable in local development. Demo routes
    # use a fixed bundled fixture internally; DEMO_ENABLED must not reopen this arbitrary-read
    # surface. Production requires repository-id or integration-handle sources.
    if not get_settings().allows_local_path_scan:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "local filesystem scanning is disabled; provide a repository integration instead",
        )
    repository_id, profile = _service(session, org).scan(body.path, body.name)
    return ScanResponse(repository_id=repository_id, profile=profile)


@router.get(
    "/repositories/{repository_id}/profile",
    response_model=RepositoryIntelligenceProfile,
    tags=["repositories"],
)
def get_repository_profile(
    repository_id: UUID,
    org: OrgContext = Depends(require_org),
    session: Session = Depends(get_db),
) -> RepositoryIntelligenceProfile:
    profile = _service(session, org).get_profile(repository_id)
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "repository profile not found")
    return profile


@router.post("/placements/plan", response_model=PlacementPlanResponse, tags=["placements"])
def create_placement_plan(
    body: RepositoryRef,
    org: OrgContext = Depends(require_org),
    session: Session = Depends(get_db),
) -> PlacementPlanResponse:
    plan_id, context_id, plan = _guard(lambda: _service(session, org).plan(body.repository_id))
    return PlacementPlanResponse(
        placement_plan_id=plan_id, context_profile_id=context_id, plan=plan
    )


@router.post("/decoys/generate", response_model=DecoyPlanResponse, tags=["decoys"])
def generate_decoys(
    body: RepositoryRef,
    org: OrgContext = Depends(require_org),
    session: Session = Depends(get_db),
) -> DecoyPlanResponse:
    decoy_plan_id, plan = _guard(lambda: _service(session, org).generate(body.repository_id))
    return DecoyPlanResponse(decoy_plan_id=decoy_plan_id, plan=plan)


@router.post("/validation/evaluate", response_model=ValidationResponse, tags=["validation"])
def evaluate_decoys(
    body: DecoyPlanRef,
    org: OrgContext = Depends(require_org),
    session: Session = Depends(get_db),
) -> ValidationResponse:
    reports = _guard(lambda: _service(session, org).evaluate(body.decoy_plan_id))
    return ValidationResponse(decoy_plan_id=body.decoy_plan_id, reports=reports)


@router.post("/monitoring/events", response_model=MonitoringEventResponse, tags=["monitoring"])
def ingest_monitoring_event(
    body: MonitoringEventRequest,
    org: OrgContext = Depends(require_org),
    session: Session = Depends(get_db),
) -> MonitoringEventResponse:
    settings = get_settings()
    if len(body.value.encode("utf-8")) > settings.monitoring_max_value_bytes:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "monitoring value exceeds the maximum size"
        )
    if not rate_limiter.allow(
        f"monitor:{org.organization_id}", settings.monitoring_rate_limit_per_minute
    ):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "monitoring rate limit exceeded")
    event, alert = _guard(
        lambda: _service(session, org).ingest_event(
            body.decoy_plan_id, body.surface, body.location, body.value
        )
    )
    return MonitoringEventResponse(detected=event is not None, event=event, alert=alert)


@router.get("/alerts", response_model=AlertListResponse, tags=["alerts"])
def list_alerts(
    org: OrgContext = Depends(require_org), session: Session = Depends(get_db)
) -> AlertListResponse:
    return AlertListResponse(alerts=_service(session, org).alerts())


@router.get("/incidents", response_model=IncidentListResponse, tags=["incidents"])
def list_incidents(
    org: OrgContext = Depends(require_org), session: Session = Depends(get_db)
) -> IncidentListResponse:
    return IncidentListResponse(incidents=_service(session, org).incidents())


def _guard[Result](action: Callable[[], Result]) -> Result:
    """Run a use case, mapping known service errors to safe HTTP responses."""
    try:
        return action()
    except ArtifactTooLargeError as error:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "artifact exceeds the maximum size"
        ) from error
    except PipelineError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
