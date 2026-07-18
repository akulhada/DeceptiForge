# Purpose: provide a minimal, development-safe organization/auth boundary.
# Responsibilities: resolve the requesting organization from headers under a simple API-key stub;
#   bypass to the demo organization only when auth is explicitly disabled. This is intentionally
#   NOT user management, OAuth, or RBAC. Dependencies: settings and the demo-org constant.
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, Header, HTTPException, status

from app.config.constants import DEMO_ORGANIZATION_ID
from app.config.settings import Settings, get_settings


@dataclass(frozen=True)
class OrgContext:
    """The authenticated organization for a request."""

    organization_id: UUID


def require_org(
    x_deceptiforge_org_id: str | None = Header(default=None),
    x_deceptiforge_api_key: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> OrgContext:
    """Resolve the organization for a request.

    When AUTH_ENABLED is false (development only) the demo organization is returned so the local
    demo works without headers. Otherwise an API key is required and it is bound to exactly one
    organization: a request may not use one shared key to act as an arbitrary organization.
    """
    if not settings.auth_enabled and settings.is_development:
        return OrgContext(DEMO_ORGANIZATION_ID)
    if not settings.auth_enabled:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "authentication bypass is restricted to development"
        )
    if not x_deceptiforge_api_key:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing API key")

    bound = settings.api_key_bindings.get(x_deceptiforge_api_key)
    if bound is not None:
        # Production-safe path: the key determines the organization; a mismatching header is denied.
        bound_org = _parse_org(bound)
        if x_deceptiforge_org_id is not None and _parse_org(x_deceptiforge_org_id) != bound_org:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, "organization does not match the API key"
            )
        return OrgContext(bound_org)

    # Development shortcut only: the demo key may act for a caller-supplied organization.
    if settings.is_development and x_deceptiforge_api_key == settings.demo_api_key:
        if x_deceptiforge_org_id is None:
            return OrgContext(DEMO_ORGANIZATION_ID)
        return OrgContext(_parse_org(x_deceptiforge_org_id))

    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid API key")


def _parse_org(value: str) -> UUID:
    try:
        return UUID(value)
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid organization id") from None
