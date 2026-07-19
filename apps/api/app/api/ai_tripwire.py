# Purpose: HTTP surface for RAG/MCP connectors, the AI tripwire deployment lifecycle, and trusted
#   signed event ingestion.
# Responsibilities: connector CRUD/test and the tripwire lifecycle (create/preview/submit/approve/
#   reject/deploy/retire) with organization scoping, per-action permission, state-transition checks,
#   separation of duties, safe errors, audit, and job idempotency. Event ingestion is signed +
#   replay-protected and minimized (never stores prompts/chunks/outputs/embeddings). Classification
#   and severity are deterministic. Connector secrets are never returned. Writes run via jobs.
# Dependencies: repository, connector ports, preview, classification, minimize, monitor signing.
from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config.settings import Settings, get_settings
from app.dependencies import get_db
from app.models.domain.ai_tripwire import (
    AiEventType,
    AiTripwirePreview,
    AiTripwireStatus,
    InvalidAiTransitionError,
    MinimizedAiEvent,
    SurfaceType,
    event_surface,
)
from app.repositories.ai_tripwire import (
    AiTripwireRepository,
    ConnectorNotFoundError,
    DeploymentNotFoundError,
    new_correlation_id,
)
from app.security import require_scope
from app.services.ai_tripwire.classification import classify, severity
from app.services.ai_tripwire.connectors import (
    ConnSpec,
    FakeMcpAdapter,
    FakeRagAdapter,
    McpConnectorAdapter,
    RagConnectorAdapter,
)
from app.services.ai_tripwire.minimize import minimize_metadata
from app.services.ai_tripwire.preview import (
    AiPreviewError,
    build_mcp_preview,
    build_rag_preview,
)
from app.services.api_keys import AuthContext
from app.services.metrics import emit
from app.services.monitor_credentials import MonitorCredentialService, MonitorSignatureError
from app.services.replay import ReplayError, get_replay_guard

router = APIRouter(tags=["ai-tripwire"])


# The concrete provider adapters are environment-specific; tests monkeypatch these builders to the
# deterministic fakes. Production wiring binds real vector-store / MCP clients here.
def build_rag_adapter() -> RagConnectorAdapter:
    return FakeRagAdapter()


def build_mcp_adapter() -> McpConnectorAdapter:
    return FakeMcpAdapter()


# ---- schemas -------------------------------------------------------------------------------------


class CreateRagConnectorRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    connector_type: str = Field(min_length=1, max_length=32)
    index_or_collection: str = Field(min_length=1, max_length=255)
    namespace: str | None = Field(default=None, max_length=255)
    secret: str = Field(min_length=1, max_length=4096)  # accepted once; stored encrypted


class CreateMcpConnectorRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    server_reference: str = Field(min_length=1, max_length=512)
    transport_type: str = Field(min_length=1, max_length=32)
    secret: str | None = Field(default=None, max_length=4096)


class RagConnectorSummary(BaseModel):
    id: UUID
    name: str
    connector_type: str
    index_or_collection: str
    namespace: str | None
    status: str
    last_tested_at: datetime | None
    safe_error_code: str | None
    created_at: datetime


class McpConnectorSummary(BaseModel):
    id: UUID
    name: str
    server_reference: str
    transport_type: str
    status: str
    last_tested_at: datetime | None
    safe_error_code: str | None
    created_at: datetime


class CreateTripwireRequest(BaseModel):
    surface_type: str
    connector_id: UUID
    target_collection: str = Field(min_length=1, max_length=255)
    decoy_kind: str = Field(min_length=1, max_length=64)


class TripwireSummary(BaseModel):
    id: UUID
    surface_type: str
    connector_id: UUID
    target_collection: str
    decoy_kind: str
    status: str
    trace_id: str
    external_asset_id: str | None
    monitoring_activated: bool
    expires_at: datetime | None
    safe_failure_code: str | None
    safe_failure_message: str | None
    created_at: datetime
    updated_at: datetime


class DecisionRequest(BaseModel):
    comment: str | None = Field(default=None, max_length=2000)


class TripwireEventRequest(BaseModel):
    trace_id: str = Field(min_length=1, max_length=128)
    event_type: str
    source_id: str = Field(min_length=1, max_length=256)
    confidence: float = Field(ge=0, le=1, default=1.0)
    # Callers may include benign metadata; forbidden/oversized fields are stripped on ingest.
    metadata: dict[str, str] = Field(default_factory=dict)
    observed_at: datetime | None = None


class TripwireEventResponse(BaseModel):
    accepted: bool
    exposure_type: str
    severity: str
    event_count: int


def _rag_summary(r) -> RagConnectorSummary:  # type: ignore[no-untyped-def]
    return RagConnectorSummary(
        id=r.id, name=r.name, connector_type=r.connector_type,
        index_or_collection=r.index_or_collection, namespace=r.namespace, status=r.status,
        last_tested_at=r.last_tested_at, safe_error_code=r.safe_error_code, created_at=r.created_at,
    )


def _mcp_summary(r) -> McpConnectorSummary:  # type: ignore[no-untyped-def]
    return McpConnectorSummary(
        id=r.id, name=r.name, server_reference=r.server_reference,
        transport_type=r.transport_type, status=r.status, last_tested_at=r.last_tested_at,
        safe_error_code=r.safe_error_code, created_at=r.created_at,
    )


def _tripwire_summary(r) -> TripwireSummary:  # type: ignore[no-untyped-def]
    return TripwireSummary(
        id=r.id, surface_type=r.surface_type, connector_id=r.connector_id,
        target_collection=r.target_collection, decoy_kind=r.decoy_kind, status=r.status,
        trace_id=r.trace_id, external_asset_id=r.external_asset_id,
        monitoring_activated=r.monitoring_activated_at is not None, expires_at=r.expires_at,
        safe_failure_code=r.safe_failure_code, safe_failure_message=r.safe_failure_message,
        created_at=r.created_at, updated_at=r.updated_at,
    )


# ---- helpers -------------------------------------------------------------------------------------


def _repo(session: Session, settings: Settings) -> AiTripwireRepository:
    return AiTripwireRepository(session, settings)


def _require_ai(settings: Settings) -> None:
    if not settings.ai_tripwire_deployment_enabled:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "AI tripwire deployment is not enabled")


def _require_rag(settings: Settings) -> None:
    if not settings.rag_connectors_enabled:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "RAG connectors are not enabled")


def _require_mcp(settings: Settings) -> None:
    if not settings.mcp_connectors_enabled:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "MCP connectors are not enabled")


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "unknown")


def _deployment(repo: AiTripwireRepository, auth: AuthContext, deployment_id: UUID):  # type: ignore[no-untyped-def]
    try:
        return repo.get_deployment(auth.organization_id, deployment_id)
    except DeploymentNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "deployment not found") from None


def _transition(repo, record, target: AiTripwireStatus, **fields):  # type: ignore[no-untyped-def]
    try:
        repo.transition(record, target, **fields)
    except InvalidAiTransitionError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from None


# ---- RAG connector endpoints ---------------------------------------------------------------------


@router.post("/rag-connectors", response_model=RagConnectorSummary, status_code=201)
def create_rag_connector(
    body: CreateRagConnectorRequest,
    request: Request,
    auth: AuthContext = Depends(require_scope("ai_tripwire_connectors:manage")),
    session: Session = Depends(get_db),
) -> RagConnectorSummary:
    settings = get_settings()
    _require_rag(settings)
    repo = _repo(session, settings)
    record = repo.create_rag_connector(
        organization_id=auth.organization_id, connector_type=body.connector_type, name=body.name,
        secret=body.secret, index_or_collection=body.index_or_collection,
        namespace=body.namespace, created_by_actor_id=auth.key_id,
    )
    repo.add_audit(
        organization_id=auth.organization_id, connector_id=record.id, actor_id=auth.key_id,
        event_type="connector_created", request_id=_request_id(request), safe_metadata="rag",
    )
    return _rag_summary(record)


@router.get("/rag-connectors", response_model=list[RagConnectorSummary])
def list_rag_connectors(
    auth: AuthContext = Depends(require_scope("ai_tripwire_connectors:read")),
    session: Session = Depends(get_db),
) -> list[RagConnectorSummary]:
    settings = get_settings()
    _require_rag(settings)
    rows = _repo(session, settings).list_rag_connectors(auth.organization_id)
    return [_rag_summary(r) for r in rows]


@router.post("/rag-connectors/{connector_id}/test")
def test_rag_connector(
    connector_id: UUID,
    request: Request,
    auth: AuthContext = Depends(require_scope("ai_tripwire_connectors:manage")),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    settings = get_settings()
    _require_rag(settings)
    repo = _repo(session, settings)
    try:
        connector = repo.get_rag_connector(auth.organization_id, connector_id)
    except ConnectorNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "connector not found") from None
    spec = ConnSpec(
        connector.index_or_collection, repo.resolve_secret(connector.secret_ciphertext),
        not settings.is_development,
    )
    result = build_rag_adapter().test_connection(spec)
    ok = result.reachable and result.authenticated and (
        result.tls_ok or settings.is_development
    )
    repo.set_rag_status(
        connector, "active" if ok else "failed", error=result.safe_error_code, tested=True
    )
    repo.add_audit(
        organization_id=auth.organization_id, connector_id=connector_id, actor_id=auth.key_id,
        event_type="connector_tested", request_id=_request_id(request), safe_metadata="rag",
    )
    return {
        "reachable": result.reachable, "tls_ok": result.tls_ok,
        "authenticated": result.authenticated, "status": connector.status,
    }


# ---- MCP connector endpoints ---------------------------------------------------------------------


@router.post("/mcp-connectors", response_model=McpConnectorSummary, status_code=201)
def create_mcp_connector(
    body: CreateMcpConnectorRequest,
    request: Request,
    auth: AuthContext = Depends(require_scope("ai_tripwire_connectors:manage")),
    session: Session = Depends(get_db),
) -> McpConnectorSummary:
    settings = get_settings()
    _require_mcp(settings)
    if (
        settings.ai_tripwire_allowed_mcp_servers
        and body.server_reference not in settings.ai_tripwire_allowed_mcp_servers
    ):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "MCP server is not in the allowlist")
    repo = _repo(session, settings)
    record = repo.create_mcp_connector(
        organization_id=auth.organization_id, name=body.name,
        server_reference=body.server_reference, transport_type=body.transport_type,
        secret=body.secret, created_by_actor_id=auth.key_id,
    )
    repo.add_audit(
        organization_id=auth.organization_id, connector_id=record.id, actor_id=auth.key_id,
        event_type="connector_created", request_id=_request_id(request), safe_metadata="mcp",
    )
    return _mcp_summary(record)


@router.get("/mcp-connectors", response_model=list[McpConnectorSummary])
def list_mcp_connectors(
    auth: AuthContext = Depends(require_scope("ai_tripwire_connectors:read")),
    session: Session = Depends(get_db),
) -> list[McpConnectorSummary]:
    settings = get_settings()
    _require_mcp(settings)
    rows = _repo(session, settings).list_mcp_connectors(auth.organization_id)
    return [_mcp_summary(r) for r in rows]


@router.post("/mcp-connectors/{connector_id}/test")
def test_mcp_connector(
    connector_id: UUID,
    request: Request,
    auth: AuthContext = Depends(require_scope("ai_tripwire_connectors:manage")),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    settings = get_settings()
    _require_mcp(settings)
    repo = _repo(session, settings)
    try:
        connector = repo.get_mcp_connector(auth.organization_id, connector_id)
    except ConnectorNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "connector not found") from None
    spec = ConnSpec(
        connector.server_reference, repo.resolve_secret(connector.secret_ciphertext),
        not settings.is_development,
    )
    result = build_mcp_adapter().test_connection(spec)
    ok = result.reachable and (result.tls_ok or settings.is_development)
    repo.set_mcp_status(
        connector, "active" if ok else "failed", error=result.safe_error_code, tested=True
    )
    repo.add_audit(
        organization_id=auth.organization_id, connector_id=connector_id, actor_id=auth.key_id,
        event_type="connector_tested", request_id=_request_id(request), safe_metadata="mcp",
    )
    return {"reachable": result.reachable, "tls_ok": result.tls_ok, "status": connector.status}


# ---- tripwire deployment endpoints ---------------------------------------------------------------


@router.post("/ai-tripwire-deployments", response_model=TripwireSummary, status_code=201)
def create_tripwire(
    body: CreateTripwireRequest,
    request: Request,
    auth: AuthContext = Depends(require_scope("ai_tripwires:create")),
    session: Session = Depends(get_db),
) -> TripwireSummary:
    settings = get_settings()
    _require_ai(settings)
    try:
        surface = SurfaceType(body.surface_type)
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "unknown surface type") from None
    repo = _repo(session, settings)
    # Validate connector ownership before drafting.
    try:
        if surface == SurfaceType.RAG_DOCUMENT:
            repo.get_rag_connector(auth.organization_id, body.connector_id)
        else:
            repo.get_mcp_connector(auth.organization_id, body.connector_id)
    except ConnectorNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "connector not found") from None
    trace = f"DFAI-{secrets.token_hex(6)}"
    expires_at = datetime.now(UTC) + timedelta(days=settings.ai_tripwire_default_expiry_days)
    record = repo.create_deployment(
        organization_id=auth.organization_id, surface_type=surface.value,
        connector_id=body.connector_id, target_collection=body.target_collection,
        decoy_kind=body.decoy_kind, trace_id=trace, requested_by_actor_id=auth.key_id,
        expires_at=expires_at,
    )
    try:
        if surface == SurfaceType.RAG_DOCUMENT:
            preview, _ = build_rag_preview(
                deployment_id=str(record.id), connector_id=str(body.connector_id),
                target_collection=body.target_collection, decoy_kind=body.decoy_kind,
                trace_token=trace, expires_at=expires_at, settings=settings,
            )
        else:
            preview, _ = build_mcp_preview(
                deployment_id=str(record.id), connector_id=str(body.connector_id),
                target_collection=body.target_collection, decoy_kind=body.decoy_kind,
                trace_token=trace, surface=surface, expires_at=expires_at, settings=settings,
            )
    except AiPreviewError as error:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(error)) from None
    repo.set_preview(record, preview)
    repo.add_audit(
        organization_id=auth.organization_id, deployment_id=record.id, actor_id=auth.key_id,
        event_type="tripwire_drafted", request_id=_request_id(request),
    )
    return _tripwire_summary(record)


@router.get("/ai-tripwire-deployments", response_model=list[TripwireSummary])
def list_tripwires(
    auth: AuthContext = Depends(require_scope("ai_tripwires:read")),
    session: Session = Depends(get_db),
) -> list[TripwireSummary]:
    settings = get_settings()
    _require_ai(settings)
    rows = _repo(session, settings).list_deployments(auth.organization_id)
    return [_tripwire_summary(r) for r in rows]


@router.get("/ai-tripwire-deployments/{deployment_id}", response_model=TripwireSummary)
def get_tripwire(
    deployment_id: UUID,
    auth: AuthContext = Depends(require_scope("ai_tripwires:read")),
    session: Session = Depends(get_db),
) -> TripwireSummary:
    settings = get_settings()
    _require_ai(settings)
    return _tripwire_summary(_deployment(_repo(session, settings), auth, deployment_id))


@router.get("/ai-tripwire-deployments/{deployment_id}/preview", response_model=AiTripwirePreview)
def get_tripwire_preview(
    deployment_id: UUID,
    auth: AuthContext = Depends(require_scope("ai_tripwires:read")),
    session: Session = Depends(get_db),
) -> AiTripwirePreview:
    settings = get_settings()
    _require_ai(settings)
    repo = _repo(session, settings)
    preview = repo.load_preview(_deployment(repo, auth, deployment_id))
    if preview is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no preview generated")
    return preview


@router.post("/ai-tripwire-deployments/{deployment_id}/submit", response_model=TripwireSummary)
def submit_tripwire(
    deployment_id: UUID,
    request: Request,
    auth: AuthContext = Depends(require_scope("ai_tripwires:create")),
    session: Session = Depends(get_db),
) -> TripwireSummary:
    settings = get_settings()
    _require_ai(settings)
    repo = _repo(session, settings)
    record = _deployment(repo, auth, deployment_id)
    _transition(repo, record, AiTripwireStatus.AWAITING_APPROVAL)
    repo.add_audit(
        organization_id=auth.organization_id, deployment_id=deployment_id, actor_id=auth.key_id,
        event_type="submitted", request_id=_request_id(request),
    )
    return _tripwire_summary(record)


@router.post("/ai-tripwire-deployments/{deployment_id}/approve", response_model=TripwireSummary)
def approve_tripwire(
    deployment_id: UUID,
    body: DecisionRequest,
    request: Request,
    auth: AuthContext = Depends(require_scope("ai_tripwires:approve")),
    session: Session = Depends(get_db),
) -> TripwireSummary:
    settings = get_settings()
    _require_ai(settings)
    repo = _repo(session, settings)
    record = _deployment(repo, auth, deployment_id)
    if (
        settings.require_separate_ai_tripwire_approver
        and auth.key_id is not None
        and record.requested_by_actor_id is not None
        and auth.key_id == record.requested_by_actor_id
    ):
        repo.add_audit(
            organization_id=auth.organization_id, deployment_id=deployment_id, actor_id=auth.key_id,
            event_type="permission_denied", request_id=_request_id(request),
            safe_metadata="separation_of_duties",
        )
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "a separate actor must approve this deployment"
        )
    _transition(repo, record, AiTripwireStatus.APPROVED, approved_by_actor_id=auth.key_id)
    repo.add_audit(
        organization_id=auth.organization_id, deployment_id=deployment_id, actor_id=auth.key_id,
        event_type="approved", request_id=_request_id(request),
    )
    return _tripwire_summary(record)


@router.post("/ai-tripwire-deployments/{deployment_id}/reject", response_model=TripwireSummary)
def reject_tripwire(
    deployment_id: UUID,
    body: DecisionRequest,
    request: Request,
    auth: AuthContext = Depends(require_scope("ai_tripwires:approve")),
    session: Session = Depends(get_db),
) -> TripwireSummary:
    settings = get_settings()
    _require_ai(settings)
    repo = _repo(session, settings)
    record = _deployment(repo, auth, deployment_id)
    _transition(repo, record, AiTripwireStatus.REJECTED)
    repo.add_audit(
        organization_id=auth.organization_id, deployment_id=deployment_id, actor_id=auth.key_id,
        event_type="rejected", request_id=_request_id(request),
    )
    return _tripwire_summary(record)


def _lifecycle(
    session: Session, auth: AuthContext, request: Request, deployment_id: UUID,
    *, target: AiTripwireStatus, job_type: str, event: str,
) -> TripwireSummary:
    settings = get_settings()
    _require_ai(settings)
    repo = _repo(session, settings)
    record = _deployment(repo, auth, deployment_id)
    _transition(repo, record, target)
    repo.clear_job(deployment_id, job_type)
    repo.enqueue_job(
        organization_id=auth.organization_id, deployment_id=deployment_id, job_type=job_type,
        correlation_id=new_correlation_id(),
    )
    repo.add_audit(
        organization_id=auth.organization_id, deployment_id=deployment_id, actor_id=auth.key_id,
        event_type=event, request_id=_request_id(request),
    )
    return _tripwire_summary(record)


@router.post("/ai-tripwire-deployments/{deployment_id}/deploy", response_model=TripwireSummary)
def deploy_tripwire(
    deployment_id: UUID,
    request: Request,
    auth: AuthContext = Depends(require_scope("ai_tripwires:deploy")),
    session: Session = Depends(get_db),
) -> TripwireSummary:
    return _lifecycle(
        session, auth, request, deployment_id,
        target=AiTripwireStatus.DEPLOYING, job_type="execute", event="deployment_started",
    )


@router.post("/ai-tripwire-deployments/{deployment_id}/retire", response_model=TripwireSummary)
def retire_tripwire(
    deployment_id: UUID,
    request: Request,
    auth: AuthContext = Depends(require_scope("ai_tripwires:retire")),
    session: Session = Depends(get_db),
) -> TripwireSummary:
    return _lifecycle(
        session, auth, request, deployment_id,
        target=AiTripwireStatus.RETIRING, job_type="retire", event="retirement_started",
    )


@router.get("/ai-tripwire-deployments/{deployment_id}/events")
def list_tripwire_events(
    deployment_id: UUID,
    auth: AuthContext = Depends(require_scope("ai_tripwires:read")),
    session: Session = Depends(get_db),
) -> list[dict[str, object]]:
    settings = get_settings()
    _require_ai(settings)
    repo = _repo(session, settings)
    _deployment(repo, auth, deployment_id)  # ownership check
    return [
        {
            "id": str(e.id), "trace_id": e.trace_id, "surface_type": e.surface_type,
            "event_type": e.event_type, "source_id": e.source_id,
            "monitor_identity": e.monitor_identity, "confidence": e.confidence,
            "minimized_metadata": e.minimized_metadata, "observed_at": e.observed_at.isoformat(),
        }
        for e in repo.events_for(deployment_id)
    ]


# ---- signed, minimized event ingestion -----------------------------------------------------------


async def _raw_body(request: Request) -> bytes:
    return await request.body()


@router.post("/ai-tripwire-events", response_model=TripwireEventResponse, tags=["ai-tripwire"])
def ingest_tripwire_event(
    body: TripwireEventRequest,
    request: Request,
    raw_body: bytes = Depends(_raw_body),
    auth: AuthContext = Depends(require_scope("ai_tripwires:ingest")),
    session: Session = Depends(get_db),
    x_deceptiforge_nonce: str | None = Header(default=None),
    x_deceptiforge_timestamp: str | None = Header(default=None),
    x_deceptiforge_monitor_id: str | None = Header(default=None),
    x_deceptiforge_signature: str | None = Header(default=None),
) -> TripwireEventResponse:
    settings = get_settings()
    _require_ai(settings)
    request_id = _request_id(request)
    org = str(auth.organization_id)
    repo = _repo(session, settings)
    try:
        event_type = AiEventType(body.event_type)
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "unknown event type") from None
    # Tamper-evidence: verify the signed request before trusting it, exactly as monitoring ingest.
    if settings.auth_enabled and settings.monitor_signature_required:
        try:
            MonitorCredentialService(session, settings).verify_request(
                organization_id=auth.organization_id, monitor_id=x_deceptiforge_monitor_id,
                timestamp=x_deceptiforge_timestamp, nonce=x_deceptiforge_nonce,
                signature=x_deceptiforge_signature, method=request.method,
                path=request.url.path, body=raw_body,
            )
        except MonitorSignatureError as error:
            emit("ai_tripwire_signature_failed", request_id=request_id, organization_id=org)
            raise HTTPException(error.status_code, error.message) from None
    if settings.auth_enabled:
        try:
            get_replay_guard().check(
                x_deceptiforge_nonce, x_deceptiforge_timestamp, scope=org
            )
        except ReplayError as error:
            emit("ai_tripwire_replay_rejected", request_id=request_id, organization_id=org)
            raise HTTPException(error.status_code, error.message) from None
    deployment = repo.find_by_trace(auth.organization_id, body.trace_id)
    if deployment is None:
        emit("ai_tripwire_event_rejected", reason="unknown_trace", organization_id=org)
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no tripwire matches the trace")
    # Monitoring is only trusted once the external asset was verified and activated.
    if deployment.monitoring_activated_at is None:
        emit("ai_tripwire_event_rejected", reason="not_monitoring", organization_id=org)
        raise HTTPException(status.HTTP_409_CONFLICT, "tripwire monitoring is not active")
    surface = event_surface(event_type)
    event = MinimizedAiEvent(
        deployment_id=str(deployment.id), trace_id=body.trace_id, surface_type=surface,
        event_type=event_type, source_id=body.source_id[:256],
        monitor_identity=(x_deceptiforge_monitor_id or "unsigned-dev")[:128],
        confidence=body.confidence, minimized_metadata=minimize_metadata(body.metadata),
        observed_at=body.observed_at or datetime.now(UTC),
    )
    repo.add_event(auth.organization_id, event)
    repo.add_audit(
        organization_id=auth.organization_id, deployment_id=deployment.id,
        event_type="event_accepted", request_id=request_id, safe_metadata=event_type.value,
    )
    # Deterministic classification + severity over the deployment's minimized events. GPT is never
    # consulted for either.
    stored = repo.events_for(deployment.id)
    event_types = frozenset(AiEventType(e.event_type) for e in stored)
    surfaces = {event_surface(t) for t in event_types}
    exposure = classify(event_types)
    sev = severity(
        exposure, event_count=len(stored),
        distinct_sources=len({e.source_id for e in stored}), surface_count=len(surfaces),
    )
    emit(
        "ai_tripwire_event_accepted", request_id=request_id, organization_id=org,
        exposure=exposure.value, severity=sev.value,
    )
    return TripwireEventResponse(
        accepted=True, exposure_type=exposure.value, severity=sev.value, event_count=len(stored)
    )
