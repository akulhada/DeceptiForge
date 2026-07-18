# Purpose: expose the deception pipeline over HTTP.
# Responsibilities: translate requests into PipelineService use cases and map missing prerequisites
#   to HTTP errors. It holds no business logic. Dependencies: the service, repository, and schemas.
from __future__ import annotations

from collections.abc import Callable
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status
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
from app.security import require_scope
from app.services.api_keys import AuthContext
from app.services.pipeline import PipelineError, PipelineService
from app.services.rate_limit import rate_limiter
from app.services.replay import ReplayError, replay_guard

router = APIRouter()


def _service(session: Session, auth: AuthContext) -> PipelineService:
    repository = ArtifactRepository(session, get_settings().max_artifact_bytes)
    return PipelineService(repository, auth.organization_id)


@router.post("/repositories/scan", response_model=ScanResponse, tags=["repositories"])
def scan_repository(
    body: ScanRequest,
    auth: AuthContext = Depends(require_scope("repositories:write")),
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
    repository_id, profile = _service(session, auth).scan(body.path, body.name)
    return ScanResponse(repository_id=repository_id, profile=profile)


@router.get(
    "/repositories/{repository_id}/profile",
    response_model=RepositoryIntelligenceProfile,
    tags=["repositories"],
)
def get_repository_profile(
    repository_id: UUID,
    auth: AuthContext = Depends(require_scope("repositories:read")),
    session: Session = Depends(get_db),
) -> RepositoryIntelligenceProfile:
    profile = _service(session, auth).get_profile(repository_id)
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "repository profile not found")
    return profile


@router.post("/placements/plan", response_model=PlacementPlanResponse, tags=["placements"])
def create_placement_plan(
    body: RepositoryRef,
    auth: AuthContext = Depends(require_scope("placements:write")),
    session: Session = Depends(get_db),
) -> PlacementPlanResponse:
    plan_id, context_id, plan = _guard(lambda: _service(session, auth).plan(body.repository_id))
    return PlacementPlanResponse(
        placement_plan_id=plan_id, context_profile_id=context_id, plan=plan
    )


@router.post("/decoys/generate", response_model=DecoyPlanResponse, tags=["decoys"])
def generate_decoys(
    body: RepositoryRef,
    auth: AuthContext = Depends(require_scope("decoys:write")),
    session: Session = Depends(get_db),
) -> DecoyPlanResponse:
    decoy_plan_id, plan = _guard(lambda: _service(session, auth).generate(body.repository_id))
    return DecoyPlanResponse(decoy_plan_id=decoy_plan_id, plan=plan)


@router.post("/validation/evaluate", response_model=ValidationResponse, tags=["validation"])
def evaluate_decoys(
    body: DecoyPlanRef,
    auth: AuthContext = Depends(require_scope("validation:write")),
    session: Session = Depends(get_db),
) -> ValidationResponse:
    reports = _guard(lambda: _service(session, auth).evaluate(body.decoy_plan_id))
    return ValidationResponse(decoy_plan_id=body.decoy_plan_id, reports=reports)


@router.post("/monitoring/events", response_model=MonitoringEventResponse, tags=["monitoring"])
def ingest_monitoring_event(
    body: MonitoringEventRequest,
    auth: AuthContext = Depends(require_scope("monitoring:ingest")),
    session: Session = Depends(get_db),
    x_deceptiforge_nonce: str | None = Header(default=None),
    x_deceptiforge_timestamp: str | None = Header(default=None),
) -> MonitoringEventResponse:
    settings = get_settings()
    # Reject oversized values before any expensive matching/hashing/persistence.
    if len(body.value.encode("utf-8")) > settings.monitoring_max_value_bytes:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "monitoring value exceeds the maximum size"
        )
    # Replay protection is enforced for real (non-development-bypass) ingestion.
    if settings.auth_enabled:
        try:
            replay_guard.check(x_deceptiforge_nonce, x_deceptiforge_timestamp)
        except ReplayError as error:
            raise HTTPException(error.status_code, error.message) from None
    if not rate_limiter.allow(
        f"monitor:{auth.organization_id}", settings.monitoring_rate_limit_per_minute
    ):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "monitoring rate limit exceeded")
    event, alert = _guard(
        lambda: _service(session, auth).ingest_event(
            body.decoy_plan_id, body.surface, body.location, body.value
        )
    )
    return MonitoringEventResponse(detected=event is not None, event=event, alert=alert)


@router.get("/alerts", response_model=AlertListResponse, tags=["alerts"])
def list_alerts(
    auth: AuthContext = Depends(require_scope("alerts:read")), session: Session = Depends(get_db)
) -> AlertListResponse:
    return AlertListResponse(alerts=_service(session, auth).alerts())


@router.get("/incidents", response_model=IncidentListResponse, tags=["incidents"])
def list_incidents(
    auth: AuthContext = Depends(require_scope("incidents:read")), session: Session = Depends(get_db)
) -> IncidentListResponse:
    return IncidentListResponse(incidents=_service(session, auth).incidents())


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
