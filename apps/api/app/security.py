# Purpose: provide the request authentication and authorization boundary.
# Responsibilities: resolve the organization and scopes from a hashed API key, keep the development
#   bypass restricted to development, and expose scope-checking dependencies. This is a scoped
#   API-key model, not full user identity/OAuth/RBAC. Dependencies: settings, key service, session.
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.config.constants import DEMO_ORGANIZATION_ID
from app.config.settings import Settings, get_settings
from app.dependencies import get_db
from app.services.api_keys import PERMISSIONS, ApiKeyService, AuthContext, AuthError, write_audit


@dataclass(frozen=True)
class OrgContext:
    organization_id: UUID


def _record_rejection(
    session: Session,
    *,
    action: str,
    request_id: str,
    organization_id: UUID | None = None,
    detail: str,
) -> None:
    """Persist a rejected security decision before its request transaction is rolled back."""
    write_audit(
        session,
        action=action,
        outcome="rejected",
        request_id=request_id,
        organization_id=organization_id,
        detail=detail,
    )
    session.commit()


def _parse_org(value: str, *, session: Session | None = None, request_id: str = "unknown") -> UUID:
    try:
        return UUID(value)
    except ValueError:
        if session is not None:
            _record_rejection(
                session,
                action="authz",
                request_id=request_id,
                detail="invalid organization id",
            )
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid organization id") from None


def _authenticate(
    request: Request,
    session: Session,
    settings: Settings,
    api_key: str | None,
    org_id: str | None,
) -> AuthContext:
    request_id = getattr(request.state, "request_id", "unknown")

    if not settings.auth_enabled and settings.is_development:
        return AuthContext(DEMO_ORGANIZATION_ID, PERMISSIONS, "owner", None)
    if not settings.auth_enabled:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "authentication bypass is restricted to development"
        )
    if not api_key:
        _record_rejection(session, action="auth", request_id=request_id, detail="missing key")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing API key")

    # Development-only static key shortcut (never enabled outside development).
    if settings.is_development and api_key == settings.demo_api_key:
        organization = (
            _parse_org(org_id, session=session, request_id=request_id)
            if org_id
            else DEMO_ORGANIZATION_ID
        )
        return AuthContext(organization, PERMISSIONS, "owner", None)

    # Env-provisioned bootstrap key bound to one organization (owner scope). Disabled by default and
    # only honored inside an explicitly opened, time-boxed bootstrap window; used solely to mint the
    # first DB-backed owner key. Every use is audited and never grants implicit permanent access.
    bound = settings.api_key_bindings.get(api_key)
    if bound is not None:
        if not settings.bootstrap_active(datetime.now(UTC)):
            _record_rejection(
                session,
                action="auth",
                request_id=request_id,
                detail="bootstrap key rejected (disabled or expired)",
            )
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid API key")
        bound_org = _parse_org(bound, session=session, request_id=request_id)
        if (
            org_id is not None
            and _parse_org(org_id, session=session, request_id=request_id) != bound_org
        ):
            _record_rejection(
                session,
                action="authz",
                request_id=request_id,
                organization_id=bound_org,
                detail="cross-org header",
            )
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, "organization does not match the API key"
            )
        write_audit(
            session,
            action="bootstrap_auth_used",
            outcome="accepted",
            request_id=request_id,
            organization_id=bound_org,
            detail="bootstrap key authenticated",
        )
        return AuthContext(bound_org, PERMISSIONS, "owner", None)

    try:
        context = ApiKeyService(session).authenticate(api_key)
    except AuthError as error:
        _record_rejection(session, action="auth", request_id=request_id, detail=error.message)
        raise HTTPException(error.status_code, error.message) from None

    if (
        org_id is not None
        and _parse_org(org_id, session=session, request_id=request_id) != context.organization_id
    ):
        _record_rejection(
            session,
            action="authz",
            request_id=request_id,
            organization_id=context.organization_id,
            detail="cross-org header",
        )
        raise HTTPException(status.HTTP_403_FORBIDDEN, "organization does not match the API key")
    return context


def require_org(
    request: Request,
    x_deceptiforge_org_id: str | None = Header(default=None),
    x_deceptiforge_api_key: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
    session: Session = Depends(get_db),
) -> OrgContext:
    context = _authenticate(
        request, session, settings, x_deceptiforge_api_key, x_deceptiforge_org_id
    )
    return OrgContext(context.organization_id)


def current_auth(
    request: Request,
    x_deceptiforge_org_id: str | None = Header(default=None),
    x_deceptiforge_api_key: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
    session: Session = Depends(get_db),
) -> AuthContext:
    """Authenticate and return the full context (organization, role, scopes)."""
    return _authenticate(request, session, settings, x_deceptiforge_api_key, x_deceptiforge_org_id)


def require_scope(scope: str):  # type: ignore[no-untyped-def]
    """Return a dependency that authenticates and requires a specific permission scope."""

    def dependency(
        request: Request,
        x_deceptiforge_org_id: str | None = Header(default=None),
        x_deceptiforge_api_key: str | None = Header(default=None),
        settings: Settings = Depends(get_settings),
        session: Session = Depends(get_db),
    ) -> AuthContext:
        context = _authenticate(
            request, session, settings, x_deceptiforge_api_key, x_deceptiforge_org_id
        )
        if scope not in context.scopes:
            request_id = getattr(request.state, "request_id", "unknown")
            _record_rejection(
                session,
                action="authz",
                request_id=request_id,
                organization_id=context.organization_id,
                detail=f"missing {scope}",
            )
            raise HTTPException(status.HTTP_403_FORBIDDEN, "insufficient permissions")
        return context

    return dependency
