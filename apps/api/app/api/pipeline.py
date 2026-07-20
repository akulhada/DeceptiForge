# Purpose: expose the deception pipeline over HTTP.
# Responsibilities: translate requests into PipelineService use cases and map missing prerequisites
#   to HTTP errors. It holds no business logic. Dependencies: the service, repository, and schemas.
from __future__ import annotations

from collections.abc import Callable
from time import perf_counter
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
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
from app.services.capacity import MonitoringQuotaGate, TenantCapacityService
from app.services.metrics import emit
from app.services.monitor_credentials import MonitorCredentialService, MonitorSignatureError
from app.services.onboarding import OnboardingService
from app.services.pipeline import PipelineError, PipelineService
from app.services.rate_limit import get_rate_limiter, rate_limit_key
from app.services.replay import ReplayError, get_replay_guard

router = APIRouter()


async def _raw_body(request: Request) -> bytes:
    """Capture the exact received request bytes for body-hash signature verification.

    Starlette caches the body, so the pydantic model parameter still parses from the same bytes.
    """
    return await request.body()


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
    if not get_rate_limiter().allow(
        rate_limit_key(
            endpoint="repositories:scan", organization_id=auth.organization_id, actor=auth.key_id
        ),
        get_settings().monitoring_rate_limit_per_minute,
    ):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "scan rate limit exceeded")
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
    request: Request,
    raw_body: bytes = Depends(_raw_body),
    auth: AuthContext = Depends(require_scope("monitoring:ingest")),
    session: Session = Depends(get_db),
    x_deceptiforge_nonce: str | None = Header(default=None),
    x_deceptiforge_timestamp: str | None = Header(default=None),
    x_deceptiforge_monitor_id: str | None = Header(default=None),
    x_deceptiforge_signature: str | None = Header(default=None),
) -> MonitoringEventResponse:
    settings = get_settings()
    started = perf_counter()
    request_id = getattr(request.state, "request_id", "unknown")
    org = str(auth.organization_id)
    # Reject oversized values before any expensive matching/hashing/persistence.
    if len(body.value.encode("utf-8")) > settings.monitoring_max_value_bytes:
        emit("monitor_ingest_rejected", reason="value_too_large", request_id=request_id)
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE, "monitoring value exceeds the maximum size"
        )
    # Tamper-evidence: when signing is required, verify the HMAC over method/path/org/monitor/
    # timestamp/nonce/body-hash before trusting the request. This proves the body was not modified.
    if settings.auth_enabled and settings.monitor_signature_required:
        try:
            MonitorCredentialService(session, settings).verify_request(
                organization_id=auth.organization_id,
                monitor_id=x_deceptiforge_monitor_id,
                timestamp=x_deceptiforge_timestamp,
                nonce=x_deceptiforge_nonce,
                signature=x_deceptiforge_signature,
                method=request.method,
                path=request.url.path,
                body=raw_body,
            )
        except MonitorSignatureError as error:
            emit("monitor_signature_failed", request_id=request_id, organization_id=org)
            raise HTTPException(error.status_code, error.message) from None
    # Replay protection is enforced for real (non-development-bypass) ingestion.
    if settings.auth_enabled:
        try:
            get_replay_guard().check(
                x_deceptiforge_nonce,
                x_deceptiforge_timestamp,
                scope=str(auth.organization_id),
            )
        except ReplayError as error:
            emit("monitor_replay_rejected", request_id=request_id, organization_id=org)
            raise HTTPException(error.status_code, error.message) from None
    if not get_rate_limiter().allow(
        rate_limit_key(
            endpoint="monitoring:ingest",
            organization_id=auth.organization_id,
            actor=auth.key_id,
            resource=body.decoy_plan_id,
        ),
        settings.monitoring_rate_limit_per_minute,
    ):
        emit("rate_limit_rejected", endpoint="monitoring:ingest", organization_id=org)
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "monitoring rate limit exceeded")
    if settings.capacity_management_enabled:
        capacity = TenantCapacityService(session, settings)
        limits = capacity.limits(auth.organization_id)
        if capacity.queue_snapshot(auth.organization_id).pending_count >= limits.max_pending_jobs:
            emit("tenant_queue_rejected", queue="reconstruction", organization_id=org)
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                "tenant reconstruction queue is at capacity",
                headers={"Retry-After": "60"},
            )
        quota = MonitoringQuotaGate(settings).admit(auth.organization_id, limits)
        if not quota.accepted:
            emit("tenant_quota_rejected", reason=quota.reason, organization_id=org)
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                "tenant monitoring quota exceeded",
                headers={"Retry-After": str(quota.retry_after_seconds)},
            )
    event, alert = _guard(
        lambda: _service(session, auth).ingest_event(
            body.decoy_plan_id, body.surface, body.location, body.value
        )
    )
    # A controlled onboarding test is completed only after normal signed ingestion has created
    # its durable event (and, when applicable, alert). This path never fabricates security data.
    if event is not None and settings.onboarding_enabled:
        OnboardingService(session, settings).record_detection(
            auth.organization_id,
            event.trace_identifier,
            event.event_id,
            alert.alert_id if alert is not None else None,
        )
    emit(
        "monitor_ingest_accepted",
        request_id=request_id,
        organization_id=org,
        detected=event is not None,
        latency_ms=round((perf_counter() - started) * 1000, 2),
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
            status.HTTP_413_CONTENT_TOO_LARGE, "artifact exceeds the maximum size"
        ) from error
    except PipelineError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
