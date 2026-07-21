# Purpose: prove the tenant/platform authorization boundary — a tenant actor can never mint a
#   platform-scoped credential, escalate its own grant, or invoke a platform control-plane
#   operation, and unknown roles fail closed.
from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.services.api_keys import (
    PLATFORM_PERMISSIONS,
    PLATFORM_ROLES,
    ROLE_SCOPES,
    TENANT_GRANTABLE_ROLES,
    ApiKeyService,
    AuthError,
    assert_grantable,
)


def _key(client, org: str, role: str) -> str:  # type: ignore[no-untyped-def]
    session = client.app_session()
    _, plaintext = ApiKeyService(session).create(UUID(org), role, role)
    session.commit()
    session.close()
    return plaintext


def _headers(key: str, org: str) -> dict[str, str]:
    return {"X-DeceptiForge-API-Key": key, "X-DeceptiForge-Org-Id": org}


def _client(make_client):  # type: ignore[no-untyped-def]
    return make_client(demo_enabled=False, auth_enabled=True, app_env="development")


# ---- role catalogue is partitioned ---------------------------------------------------------------


def test_platform_and_tenant_role_sets_are_disjoint() -> None:
    assert PLATFORM_ROLES & set(TENANT_GRANTABLE_ROLES) == set()


def test_no_tenant_grantable_role_carries_a_platform_permission() -> None:
    for role in TENANT_GRANTABLE_ROLES:
        assert ROLE_SCOPES[role] & PLATFORM_PERMISSIONS == frozenset(), role


def test_platform_control_plane_permissions_are_not_in_any_tenant_role() -> None:
    """Reliability, failover, failback, backups and capacity belong to the platform plane."""
    controlled = {
        "platform:reliability",
        "platform:failover",
        "platform:failback",
        "platform:capacity",
        "platform:learning_global",
    }
    assert controlled <= PLATFORM_PERMISSIONS
    for role in TENANT_GRANTABLE_ROLES:
        assert ROLE_SCOPES[role] & controlled == set(), role


# ---- credential minting --------------------------------------------------------------------------


def test_tenant_admin_cannot_mint_an_operator_key(make_client) -> None:  # type: ignore[no-untyped-def]
    """The original escalation: a tenant admin requesting role=operator gained platform scopes."""
    with _client(make_client) as client:
        org = str(uuid4())
        key = _key(client, org, "admin")
        response = client.post(
            "/admin/api-keys",
            json={"name": "escalate", "role": "operator"},
            headers=_headers(key, org),
        )
        assert response.status_code in (400, 403)


def test_tenant_owner_cannot_mint_an_operator_key(make_client) -> None:  # type: ignore[no-untyped-def]
    with _client(make_client) as client:
        org = str(uuid4())
        key = _key(client, org, "owner")
        response = client.post(
            "/admin/api-keys",
            json={"name": "escalate", "role": "operator"},
            headers=_headers(key, org),
        )
        assert response.status_code in (400, 403)


def test_service_layer_refuses_a_platform_role_for_a_tenant_issuer(make_client) -> None:  # type: ignore[no-untyped-def]
    """Defense in depth: the service refuses even if a route forgot to check."""
    with _client(make_client) as client:
        session = client.app_session()
        service = ApiKeyService(session)
        with pytest.raises(AuthError):
            service.create(uuid4(), "escalate", "operator", issuer_scopes=ROLE_SCOPES["owner"])
        session.close()


def test_issuer_cannot_grant_beyond_its_own_scope() -> None:
    """An analyst-scoped issuer cannot mint an admin key."""
    with pytest.raises(AuthError):
        assert_grantable(ROLE_SCOPES["analyst"], "admin")
    # An owner may grant an ordinary tenant role.
    assert_grantable(ROLE_SCOPES["owner"], "analyst")


def test_unknown_role_fails_closed() -> None:
    with pytest.raises(AuthError):
        assert_grantable(ROLE_SCOPES["owner"], "wizard")


def test_sensor_roles_are_not_mintable_through_the_admin_api(make_client) -> None:  # type: ignore[no-untyped-def]
    """Sensor identities are provisioned at enrollment, never through tenant key administration."""
    with _client(make_client) as client:
        org = str(uuid4())
        key = _key(client, org, "owner")
        for role in ("browser_sensor", "agent_sensor"):
            response = client.post(
                "/admin/api-keys",
                json={"name": "sensor", "role": role},
                headers=_headers(key, org),
            )
            assert response.status_code in (400, 403), role


def test_tenant_roles_remain_mintable(make_client) -> None:  # type: ignore[no-untyped-def]
    with _client(make_client) as client:
        org = str(uuid4())
        key = _key(client, org, "owner")
        for role in ("viewer", "analyst", "admin"):
            response = client.post(
                "/admin/api-keys",
                json={"name": f"k-{role}", "role": role},
                headers=_headers(key, org),
            )
            assert response.status_code == 200, role


# ---- platform control plane ----------------------------------------------------------------------


_PLATFORM_ROUTES = [
    ("GET", "/admin/reliability/status"),
    ("GET", "/admin/reliability/backups"),
    ("GET", "/admin/reliability/failover-events"),
]


@pytest.mark.parametrize("method,path", _PLATFORM_ROUTES)
@pytest.mark.parametrize("role", ["viewer", "analyst", "admin", "owner", "service"])
def test_tenant_roles_cannot_reach_the_platform_control_plane(  # type: ignore[no-untyped-def]
    make_client, method: str, path: str, role: str
) -> None:
    with _client(make_client) as client:
        org = str(uuid4())
        key = _key(client, org, role)
        response = client.request(method, path, headers=_headers(key, org))
        assert response.status_code in (403, 404), f"{role} reached {path}"


@pytest.mark.parametrize("method,path", _PLATFORM_ROUTES)
def test_platform_routes_reject_unauthenticated_requests(  # type: ignore[no-untyped-def]
    make_client, method: str, path: str
) -> None:
    with _client(make_client) as client:
        response = client.request(method, path)
        assert response.status_code in (401, 404)
