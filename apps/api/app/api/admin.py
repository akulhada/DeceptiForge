# Purpose: admin endpoints to create, list, and revoke organization-scoped API keys.
# Responsibilities: require the admin:manage_keys scope, return a plaintext key exactly once at
#   creation, and never expose or log key material afterward. Dependencies: the key service, audit.
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config.settings import get_settings
from app.dependencies import get_db
from app.security import require_scope
from app.services.api_keys import ROLE_SCOPES, ApiKeyService, AuthContext, AuthError, write_audit
from app.services.monitor_credentials import MonitorCredentialService
from app.services.rate_limit import get_rate_limiter, rate_limit_key

router = APIRouter(prefix="/admin", tags=["admin"])


def _rate_limit(endpoint: str, auth: AuthContext) -> None:
    """Apply the shared distributed limit to a management endpoint."""
    if not get_rate_limiter().allow(
        rate_limit_key(endpoint=endpoint, organization_id=auth.organization_id, actor=auth.key_id),
        get_settings().admin_rate_limit_per_minute,
    ):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "admin rate limit exceeded")


class CreateApiKeyRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    role: str = Field(default="viewer")
    expires_at: datetime | None = None


class ApiKeySummary(BaseModel):
    id: UUID
    key_prefix: str
    name: str
    role: str
    scopes: tuple[str, ...]
    status: str
    expires_at: datetime | None
    last_used_at: datetime | None
    created_at: datetime


class CreateApiKeyResponse(BaseModel):
    api_key: str  # shown once; never retrievable again
    key: ApiKeySummary


def _summary(record) -> ApiKeySummary:  # type: ignore[no-untyped-def]
    import json

    return ApiKeySummary(
        id=record.id,
        key_prefix=record.key_prefix,
        name=record.name,
        role=record.role,
        scopes=tuple(json.loads(record.scopes)),
        status=record.status,
        expires_at=record.expires_at,
        last_used_at=record.last_used_at,
        created_at=record.created_at,
    )


@router.post("/api-keys", response_model=CreateApiKeyResponse)
def create_api_key(
    body: CreateApiKeyRequest,
    request: Request,
    auth: AuthContext = Depends(require_scope("admin:manage_keys")),
    session: Session = Depends(get_db),
) -> CreateApiKeyResponse:
    _rate_limit("admin:api_keys:create", auth)
    if body.role not in ROLE_SCOPES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "unknown role")
    try:
        record, plaintext = ApiKeyService(session).create(
            auth.organization_id, body.name, body.role, expires_at=body.expires_at
        )
    except AuthError as error:
        raise HTTPException(error.status_code, error.message) from None
    write_audit(
        session,
        action="api_key_created",
        outcome="accepted",
        request_id=getattr(request.state, "request_id", "unknown"),
        organization_id=auth.organization_id,
        detail=f"prefix={record.key_prefix} role={record.role}",
    )
    return CreateApiKeyResponse(api_key=plaintext, key=_summary(record))


@router.get("/api-keys", response_model=list[ApiKeySummary])
def list_api_keys(
    auth: AuthContext = Depends(require_scope("admin:manage_keys")),
    session: Session = Depends(get_db),
) -> list[ApiKeySummary]:
    return [_summary(record) for record in ApiKeyService(session).list(auth.organization_id)]


@router.delete("/api-keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_api_key(
    key_id: UUID,
    request: Request,
    auth: AuthContext = Depends(require_scope("admin:manage_keys")),
    session: Session = Depends(get_db),
) -> None:
    _rate_limit("admin:api_keys:revoke", auth)
    if not ApiKeyService(session).revoke(auth.organization_id, key_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "API key not found")
    write_audit(
        session,
        action="api_key_revoked",
        outcome="accepted",
        request_id=getattr(request.state, "request_id", "unknown"),
        organization_id=auth.organization_id,
        detail=f"key_id={key_id}",
    )


# ---- monitor signing credentials -----------------------------------------------------------------


class CreateMonitorCredentialRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    expires_at: datetime | None = None


class MonitorCredentialSummary(BaseModel):
    id: UUID
    monitor_id: str
    name: str
    status: str
    key_version: str
    expires_at: datetime | None
    last_used_at: datetime | None
    created_at: datetime


class CreateMonitorCredentialResponse(BaseModel):
    monitor_id: str
    signing_secret: str  # shown once; never retrievable again
    credential: MonitorCredentialSummary


def _monitor_summary(record) -> MonitorCredentialSummary:  # type: ignore[no-untyped-def]
    return MonitorCredentialSummary(
        id=record.id,
        monitor_id=record.monitor_id,
        name=record.name,
        status=record.status,
        key_version=record.secret_key_version,
        expires_at=record.expires_at,
        last_used_at=record.last_used_at,
        created_at=record.created_at,
    )


@router.post("/monitor-credentials", response_model=CreateMonitorCredentialResponse)
def create_monitor_credential(
    body: CreateMonitorCredentialRequest,
    request: Request,
    auth: AuthContext = Depends(require_scope("admin:manage_monitors")),
    session: Session = Depends(get_db),
) -> CreateMonitorCredentialResponse:
    _rate_limit("admin:monitors:create", auth)
    record, secret = MonitorCredentialService(session, get_settings()).create(
        auth.organization_id, body.name, expires_at=body.expires_at
    )
    write_audit(
        session,
        action="monitor_credential_created",
        outcome="accepted",
        request_id=getattr(request.state, "request_id", "unknown"),
        organization_id=auth.organization_id,
        detail=f"monitor_id={record.monitor_id}",
    )
    return CreateMonitorCredentialResponse(
        monitor_id=record.monitor_id,
        signing_secret=secret,
        credential=_monitor_summary(record),
    )


@router.get("/monitor-credentials", response_model=list[MonitorCredentialSummary])
def list_monitor_credentials(
    auth: AuthContext = Depends(require_scope("admin:manage_monitors")),
    session: Session = Depends(get_db),
) -> list[MonitorCredentialSummary]:
    return [
        _monitor_summary(record)
        for record in MonitorCredentialService(session, get_settings()).list(auth.organization_id)
    ]


@router.delete("/monitor-credentials/{credential_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_monitor_credential(
    credential_id: UUID,
    request: Request,
    auth: AuthContext = Depends(require_scope("admin:manage_monitors")),
    session: Session = Depends(get_db),
) -> None:
    _rate_limit("admin:monitors:revoke", auth)
    if not MonitorCredentialService(session, get_settings()).revoke(
        auth.organization_id, credential_id
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "monitor credential not found")
    write_audit(
        session,
        action="monitor_credential_revoked",
        outcome="accepted",
        request_id=getattr(request.state, "request_id", "unknown"),
        organization_id=auth.organization_id,
        detail=f"credential_id={credential_id}",
    )
