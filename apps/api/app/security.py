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

    When AUTH_ENABLED is false (development/demo only) the demo organization is returned so the
    local demo works without headers. Otherwise a valid API key and organization id are required.
    """
    if not settings.auth_enabled:
        return OrgContext(DEMO_ORGANIZATION_ID)

    if settings.demo_api_key is None or x_deceptiforge_api_key != settings.demo_api_key:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or missing API key")
    if x_deceptiforge_org_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "missing organization id")
    try:
        organization_id = UUID(x_deceptiforge_org_id)
    except ValueError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid organization id") from None
    return OrgContext(organization_id)
