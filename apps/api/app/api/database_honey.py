# Purpose: HTTP surface for PostgreSQL connectors and database honey-record deployments.
# Responsibilities: connector CRUD/test/schema-sync and the honey deployment lifecycle
#   (create/preview/submit/approve/reject/deploy/retire/rollback/rotate) with organization scoping,
#   per-action permission, state-transition checks, separation of duties, safe errors, audit, and
#   job idempotency. Connector secrets are never returned. Writes run asynchronously via jobs.
# Dependencies: repository, connector port, preview/suitability, settings, auth.
from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config.settings import Settings, get_settings
from app.dependencies import get_db
from app.models.domain.database_honey import (
    HoneyDecoyType,
    HoneyDeploymentPreview,
    HoneyDeploymentStatus,
    InvalidHoneyTransitionError,
)
from app.repositories.database_honey import (
    ConnectorNotFoundError,
    DatabaseHoneyRepository,
    HoneyDeploymentNotFoundError,
    new_correlation_id,
)
from app.security import require_scope
from app.services.api_keys import AuthContext
from app.services.database.connector_port import ConnectionSpec, DatabaseConnectorClient
from app.services.database.preview import HoneyPreviewError, build_preview
from app.services.database.psycopg_adapter import PsycopgDatabaseClient
from app.services.database.suitability import score_table

router = APIRouter(tags=["database-honey"])


def build_connector_client() -> DatabaseConnectorClient:
    """Return the real PostgreSQL client. Tests monkeypatch this to a FakeDatabaseClient."""
    return PsycopgDatabaseClient()


# ---- schemas -------------------------------------------------------------------------------------


class CreateConnectorRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    host_reference: str = Field(min_length=1, max_length=512)
    database_name: str = Field(min_length=1, max_length=255)
    user: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=1, max_length=1024)  # accepted once; stored encrypted
    ssl_mode: str = Field(default="require")
    read_only_mode: bool = True


class ConnectorSummary(BaseModel):
    id: UUID
    name: str
    host_reference: str
    database_name: str
    ssl_mode: str
    status: str
    read_only_mode: bool
    last_tested_at: datetime | None
    last_schema_sync_at: datetime | None
    safe_error_code: str | None
    created_at: datetime


class CreateHoneyDeploymentRequest(BaseModel):
    connector_id: UUID
    target_schema: str = Field(min_length=1, max_length=255)
    target_table: str = Field(min_length=1, max_length=255)
    decoy_type: str | None = None


class HoneyDeploymentSummary(BaseModel):
    id: UUID
    connector_id: UUID
    target_schema: str
    target_table: str
    decoy_type: str
    status: str
    monitoring_activated: bool
    expires_at: datetime | None
    failure_code: str | None
    safe_failure_message: str | None
    created_at: datetime
    updated_at: datetime


class DecisionRequest(BaseModel):
    comment: str | None = Field(default=None, max_length=2000)


def _connector_summary(record) -> ConnectorSummary:  # type: ignore[no-untyped-def]
    return ConnectorSummary(
        id=record.id, name=record.name, host_reference=record.host_reference,
        database_name=record.database_name, ssl_mode=record.ssl_mode, status=record.status,
        read_only_mode=record.read_only_mode, last_tested_at=record.last_tested_at,
        last_schema_sync_at=record.last_schema_sync_at, safe_error_code=record.safe_error_code,
        created_at=record.created_at,
    )


def _deployment_summary(record) -> HoneyDeploymentSummary:  # type: ignore[no-untyped-def]
    return HoneyDeploymentSummary(
        id=record.id, connector_id=record.connector_id, target_schema=record.target_schema,
        target_table=record.target_table, decoy_type=record.decoy_type, status=record.status,
        monitoring_activated=record.monitoring_activated_at is not None,
        expires_at=record.expires_at, failure_code=record.failure_code,
        safe_failure_message=record.safe_failure_message, created_at=record.created_at,
        updated_at=record.updated_at,
    )


# ---- helpers -------------------------------------------------------------------------------------


def _repo(session: Session, settings: Settings) -> DatabaseHoneyRepository:
    return DatabaseHoneyRepository(session, settings)


def _require_connectors(settings: Settings) -> None:
    if not settings.database_connectors_enabled:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "database connectors are not enabled")


def _require_honey(settings: Settings) -> None:
    if not settings.database_honey_deployment_enabled:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "database honey deployment is not enabled")


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "unknown")


def _connector(repo: DatabaseHoneyRepository, auth: AuthContext, connector_id: UUID):  # type: ignore[no-untyped-def]
    try:
        return repo.get_connector(auth.organization_id, connector_id)
    except ConnectorNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "connector not found") from None


def _deployment(repo: DatabaseHoneyRepository, auth: AuthContext, deployment_id: UUID):  # type: ignore[no-untyped-def]
    try:
        return repo.get_deployment(auth.organization_id, deployment_id)
    except HoneyDeploymentNotFoundError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "deployment not found") from None


def _transition(repo, record, target: HoneyDeploymentStatus, **fields):  # type: ignore[no-untyped-def]
    try:
        repo.transition(record, target, **fields)
    except InvalidHoneyTransitionError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from None


def _spec(repo: DatabaseHoneyRepository, connector, settings: Settings) -> ConnectionSpec:  # type: ignore[no-untyped-def]
    secret = repo.resolve_secret(connector)
    return ConnectionSpec(
        host=connector.host_reference, database=connector.database_name,
        user=str(secret.get("user", "")), password=str(secret.get("password", "")),
        ssl_mode=connector.ssl_mode,
        connect_timeout_seconds=settings.database_connect_timeout_seconds,
        statement_timeout_ms=settings.database_statement_timeout_ms,
    )


# ---- connector endpoints -------------------------------------------------------------------------


@router.post("/database-connectors", response_model=ConnectorSummary, status_code=201)
def create_connector(
    body: CreateConnectorRequest,
    request: Request,
    auth: AuthContext = Depends(require_scope("database_connectors:manage")),
    session: Session = Depends(get_db),
) -> ConnectorSummary:
    settings = get_settings()
    _require_connectors(settings)
    if settings.database_require_tls and not settings.is_development and body.ssl_mode == "disable":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "TLS is required for connectors")
    repo = _repo(session, settings)
    record = repo.create_connector(
        organization_id=auth.organization_id, name=body.name,
        host_reference=body.host_reference, database_name=body.database_name,
        secret_payload={"user": body.user, "password": body.password},
        ssl_mode=body.ssl_mode, read_only_mode=body.read_only_mode,
        created_by_actor_id=auth.key_id,
    )
    repo.add_audit(
        organization_id=auth.organization_id, connector_id=record.id, actor_id=auth.key_id,
        event_type="connector_created", request_id=_request_id(request),
    )
    return _connector_summary(record)


@router.get("/database-connectors", response_model=list[ConnectorSummary])
def list_connectors(
    auth: AuthContext = Depends(require_scope("database_connectors:read")),
    session: Session = Depends(get_db),
) -> list[ConnectorSummary]:
    settings = get_settings()
    _require_connectors(settings)
    rows = _repo(session, settings).list_connectors(auth.organization_id)
    return [_connector_summary(r) for r in rows]


@router.get("/database-connectors/{connector_id}", response_model=ConnectorSummary)
def get_connector(
    connector_id: UUID,
    auth: AuthContext = Depends(require_scope("database_connectors:read")),
    session: Session = Depends(get_db),
) -> ConnectorSummary:
    settings = get_settings()
    _require_connectors(settings)
    return _connector_summary(_connector(_repo(session, settings), auth, connector_id))


@router.post("/database-connectors/{connector_id}/test")
def test_connector(
    connector_id: UUID,
    request: Request,
    auth: AuthContext = Depends(require_scope("database_connectors:manage")),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    settings = get_settings()
    _require_connectors(settings)
    repo = _repo(session, settings)
    connector = _connector(repo, auth, connector_id)
    result = build_connector_client().test_connection(_spec(repo, connector, settings))
    ok = result.reachable and result.authenticated and (
        result.tls_ok or settings.is_development or not settings.database_require_tls
    )
    repo.set_connector_status(
        connector, "active" if ok else "failed",
        error_code=result.safe_error_code, tested=True,
    )
    repo.add_audit(
        organization_id=auth.organization_id, connector_id=connector_id, actor_id=auth.key_id,
        event_type="connector_tested", request_id=_request_id(request),
    )
    return {
        "reachable": result.reachable, "tls_ok": result.tls_ok,
        "authenticated": result.authenticated, "server_version": result.server_version,
        "read_ok": result.read_ok, "write_ok": result.write_ok,
        "statement_timeout_ok": result.statement_timeout_ok, "status": connector.status,
    }


@router.post("/database-connectors/{connector_id}/sync-schema")
def sync_schema(
    connector_id: UUID,
    request: Request,
    auth: AuthContext = Depends(require_scope("database_connectors:manage")),
    session: Session = Depends(get_db),
) -> dict[str, object]:
    settings = get_settings()
    _require_connectors(settings)
    repo = _repo(session, settings)
    connector = _connector(repo, auth, connector_id)
    snapshot = build_connector_client().discover_schema(
        _spec(repo, connector, settings),
        allowed_schemas=tuple(settings.database_allowed_schemas),
        max_tables=settings.database_max_schema_tables,
    )
    record = repo.add_snapshot(auth.organization_id, connector_id, snapshot)
    repo.set_connector_status(connector, "active", schema_synced=True)
    repo.add_audit(
        organization_id=auth.organization_id, connector_id=connector_id, actor_id=auth.key_id,
        event_type="schema_synchronized", request_id=_request_id(request),
        safe_metadata=f"tables={len(snapshot.tables)}",
    )
    return {"snapshot_id": str(record.id), "tables": len(snapshot.tables)}


@router.delete("/database-connectors/{connector_id}", status_code=204)
def delete_connector(
    connector_id: UUID,
    request: Request,
    auth: AuthContext = Depends(require_scope("database_connectors:manage")),
    session: Session = Depends(get_db),
) -> None:
    settings = get_settings()
    _require_connectors(settings)
    repo = _repo(session, settings)
    repo.delete_connector(_connector(repo, auth, connector_id))
    repo.add_audit(
        organization_id=auth.organization_id, connector_id=connector_id, actor_id=auth.key_id,
        event_type="connector_disabled", request_id=_request_id(request),
    )


# ---- honey deployment endpoints ------------------------------------------------------------------


@router.post("/database-honey-deployments", response_model=HoneyDeploymentSummary, status_code=201)
def create_deployment(
    body: CreateHoneyDeploymentRequest,
    request: Request,
    auth: AuthContext = Depends(require_scope("database_honey:create")),
    session: Session = Depends(get_db),
) -> HoneyDeploymentSummary:
    settings = get_settings()
    _require_honey(settings)
    repo = _repo(session, settings)
    connector = _connector(repo, auth, body.connector_id)
    snap_record = repo.latest_snapshot(auth.organization_id, connector.id)
    if snap_record is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "sync the connector schema first")
    snapshot = repo.get_snapshot(auth.organization_id, snap_record.id)
    table = next(
        (
            t for t in snapshot.tables
            if t.schema_name == body.target_schema and t.table_name == body.target_table
        ),
        None,
    )
    if table is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "table not found in the latest snapshot")
    recommendation = score_table(
        table, allowed_schemas=tuple(settings.database_allowed_schemas),
        blocked_patterns=tuple(settings.database_blocked_table_patterns),
    )
    if not recommendation.deployable:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "; ".join(recommendation.reasoning) or "table not eligible"
        )
    decoy_type = (
        HoneyDecoyType(body.decoy_type)
        if body.decoy_type
        else recommendation.recommended_decoy_type
    )
    expires_at = datetime.now(UTC) + timedelta(days=settings.database_default_expiry_days)
    record = repo.create_deployment(
        organization_id=auth.organization_id, connector_id=connector.id,
        schema_snapshot_id=snap_record.id, target_schema=body.target_schema,
        target_table=body.target_table, decoy_type=decoy_type.value,
        requested_by_actor_id=auth.key_id, expires_at=expires_at,
    )
    try:
        preview, _row = build_preview(
            deployment_id=str(record.id), connector_id=str(connector.id), snapshot=snapshot,
            schema=body.target_schema, table=body.target_table, decoy_type=decoy_type,
            trace_id=f"DFH-{secrets.token_hex(6)}",
            allowed_schemas=tuple(settings.database_allowed_schemas),
            blocked_patterns=tuple(settings.database_blocked_table_patterns), expires_at=expires_at,
        )
    except HoneyPreviewError as error:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(error)) from None
    repo.set_preview(record, preview)
    repo.add_audit(
        organization_id=auth.organization_id, deployment_id=record.id, actor_id=auth.key_id,
        event_type="deployment_drafted", request_id=_request_id(request),
    )
    return _deployment_summary(record)


@router.get("/database-honey-deployments", response_model=list[HoneyDeploymentSummary])
def list_deployments(
    auth: AuthContext = Depends(require_scope("database_honey:read")),
    session: Session = Depends(get_db),
) -> list[HoneyDeploymentSummary]:
    settings = get_settings()
    _require_honey(settings)
    rows = _repo(session, settings).list_deployments(auth.organization_id)
    return [_deployment_summary(r) for r in rows]


@router.get("/database-honey-deployments/{deployment_id}", response_model=HoneyDeploymentSummary)
def get_deployment(
    deployment_id: UUID,
    auth: AuthContext = Depends(require_scope("database_honey:read")),
    session: Session = Depends(get_db),
) -> HoneyDeploymentSummary:
    settings = get_settings()
    _require_honey(settings)
    return _deployment_summary(_deployment(_repo(session, settings), auth, deployment_id))


@router.get(
    "/database-honey-deployments/{deployment_id}/preview", response_model=HoneyDeploymentPreview
)
def get_preview(
    deployment_id: UUID,
    auth: AuthContext = Depends(require_scope("database_honey:read")),
    session: Session = Depends(get_db),
) -> HoneyDeploymentPreview:
    settings = get_settings()
    _require_honey(settings)
    repo = _repo(session, settings)
    preview = repo.load_preview(_deployment(repo, auth, deployment_id))
    if preview is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no preview generated")
    return preview


@router.post(
    "/database-honey-deployments/{deployment_id}/submit",
    response_model=HoneyDeploymentSummary,
)
def submit(
    deployment_id: UUID,
    request: Request,
    auth: AuthContext = Depends(require_scope("database_honey:create")),
    session: Session = Depends(get_db),
) -> HoneyDeploymentSummary:
    settings = get_settings()
    _require_honey(settings)
    repo = _repo(session, settings)
    record = _deployment(repo, auth, deployment_id)
    _transition(repo, record, HoneyDeploymentStatus.AWAITING_APPROVAL)
    repo.add_audit(
        organization_id=auth.organization_id, deployment_id=deployment_id, actor_id=auth.key_id,
        event_type="submitted", request_id=_request_id(request),
    )
    return _deployment_summary(record)


@router.post(
    "/database-honey-deployments/{deployment_id}/approve",
    response_model=HoneyDeploymentSummary,
)
def approve(
    deployment_id: UUID,
    body: DecisionRequest,
    request: Request,
    auth: AuthContext = Depends(require_scope("database_honey:approve")),
    session: Session = Depends(get_db),
) -> HoneyDeploymentSummary:
    settings = get_settings()
    _require_honey(settings)
    repo = _repo(session, settings)
    record = _deployment(repo, auth, deployment_id)
    if (
        settings.require_separate_database_approver
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
    _transition(repo, record, HoneyDeploymentStatus.APPROVED, approved_by_actor_id=auth.key_id)
    repo.add_audit(
        organization_id=auth.organization_id, deployment_id=deployment_id, actor_id=auth.key_id,
        event_type="approved", request_id=_request_id(request),
    )
    return _deployment_summary(record)


@router.post(
    "/database-honey-deployments/{deployment_id}/reject",
    response_model=HoneyDeploymentSummary,
)
def reject(
    deployment_id: UUID,
    body: DecisionRequest,
    request: Request,
    auth: AuthContext = Depends(require_scope("database_honey:approve")),
    session: Session = Depends(get_db),
) -> HoneyDeploymentSummary:
    settings = get_settings()
    _require_honey(settings)
    repo = _repo(session, settings)
    record = _deployment(repo, auth, deployment_id)
    _transition(repo, record, HoneyDeploymentStatus.REJECTED)
    repo.add_audit(
        organization_id=auth.organization_id, deployment_id=deployment_id, actor_id=auth.key_id,
        event_type="rejected", request_id=_request_id(request),
    )
    return _deployment_summary(record)


def _lifecycle(
    session: Session, auth: AuthContext, request: Request, deployment_id: UUID,
    *, target: HoneyDeploymentStatus, job_type: str, event: str,
) -> HoneyDeploymentSummary:
    settings = get_settings()
    _require_honey(settings)
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
    return _deployment_summary(record)


@router.post(
    "/database-honey-deployments/{deployment_id}/deploy",
    response_model=HoneyDeploymentSummary,
)
def deploy(
    deployment_id: UUID,
    request: Request,
    auth: AuthContext = Depends(require_scope("database_honey:deploy")),
    session: Session = Depends(get_db),
) -> HoneyDeploymentSummary:
    return _lifecycle(
        session, auth, request, deployment_id,
        target=HoneyDeploymentStatus.DEPLOYING, job_type="execute", event="deployment_started",
    )


@router.post(
    "/database-honey-deployments/{deployment_id}/retire",
    response_model=HoneyDeploymentSummary,
)
def retire(
    deployment_id: UUID,
    request: Request,
    auth: AuthContext = Depends(require_scope("database_honey:retire")),
    session: Session = Depends(get_db),
) -> HoneyDeploymentSummary:
    return _lifecycle(
        session, auth, request, deployment_id,
        target=HoneyDeploymentStatus.RETIRING, job_type="retire", event="retirement_started",
    )


@router.post(
    "/database-honey-deployments/{deployment_id}/rollback",
    response_model=HoneyDeploymentSummary,
)
def rollback(
    deployment_id: UUID,
    request: Request,
    auth: AuthContext = Depends(require_scope("database_honey:rollback")),
    session: Session = Depends(get_db),
) -> HoneyDeploymentSummary:
    return _lifecycle(
        session, auth, request, deployment_id,
        target=HoneyDeploymentStatus.ROLLBACK_PENDING, job_type="rollback",
        event="rollback_started",
    )


@router.post(
    "/database-honey-deployments/{deployment_id}/rotate",
    response_model=HoneyDeploymentSummary,
)
def rotate(
    deployment_id: UUID,
    request: Request,
    auth: AuthContext = Depends(require_scope("database_honey:deploy")),
    session: Session = Depends(get_db),
) -> HoneyDeploymentSummary:
    # Rotation retires the current row; the operator creates and approves a replacement deployment,
    # linked via replaced_by. Incident history is preserved (records are retained).
    return _lifecycle(
        session, auth, request, deployment_id,
        target=HoneyDeploymentStatus.RETIRING, job_type="retire", event="rotation_started",
    )
