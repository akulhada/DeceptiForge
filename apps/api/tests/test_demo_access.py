# Purpose: the curated demo's authorization boundary.
# Five demo routes MUTATE and, once the demo is hosted in a judge environment, they are
# internet-reachable. These tests assert they are not open there, that the demo credential is
# minimal and organization-bound, and that demo and judge sessions cannot reach each other.
from __future__ import annotations

import pytest

from app.config.constants import DEMO_ORGANIZATION_ID
from app.config.settings import get_settings
from app.dependencies import get_db
from app.services.api_keys import (
    JUDGE_PERMISSIONS,
    ROLE_SCOPES,
    TENANT_GRANTABLE_ROLES,
    ApiKeyService,
    AuthError,
    assert_grantable,
)
from app.services.judge_sandbox import JudgeSandboxService

_MUTATING = ["/demo/seed", "/demo/simulate-detection", "/demo/trigger", "/demo/reset", "/demo/run"]
_READING = ["/demo/state", "/demo/status"]


def _hosted_demo_client(make_client):  # type: ignore[no-untyped-def]
    """A judge-mode deployment hosting the curated demo."""
    return make_client(app_env="judge", auth_enabled=True, demo_enabled=True)


def _mint(client, role: str, organization_id):  # type: ignore[no-untyped-def]
    session = next(client.app.dependency_overrides.get(get_db, get_db)())
    _, plaintext = ApiKeyService(session).create(organization_id, f"test-{role}", role)
    session.commit()
    return {
        "X-DeceptiForge-API-Key": plaintext,
        "X-DeceptiForge-Org-Id": str(organization_id),
    }


class TestHostedDemoRequiresACredential:
    @pytest.mark.parametrize("path", _MUTATING)
    def test_mutating_routes_are_not_open(self, make_client, path: str) -> None:  # type: ignore[no-untyped-def]
        # These drive the real pipeline and write records. Unauthenticated access to them on an
        # internet-reachable deployment would let anyone seed, reset or replay the demo.
        with _hosted_demo_client(make_client) as client:
            assert client.post(path).status_code in (401, 403)

    @pytest.mark.parametrize("path", _READING)
    def test_reading_routes_are_not_open_either(self, make_client, path: str) -> None:  # type: ignore[no-untyped-def]
        with _hosted_demo_client(make_client) as client:
            assert client.get(path).status_code in (401, 403)

    def test_a_demo_credential_opens_them(self, make_client) -> None:  # type: ignore[no-untyped-def]
        with _hosted_demo_client(make_client) as client:
            headers = _mint(client, "demo", DEMO_ORGANIZATION_ID)
            assert client.get("/demo/state", headers=headers).status_code == 200
            assert client.post("/demo/seed", headers=headers).status_code == 200

    def test_development_keeps_the_demo_open_for_local_use(self, make_client) -> None:  # type: ignore[no-untyped-def]
        # Unchanged behaviour: local development needs no credential, the same way the demo API key
        # bypass is development-only.
        with make_client(app_env="development", demo_enabled=True) as client:
            assert client.get("/demo/state").status_code == 200


class TestDemoCredentialIsMinimal:
    def test_it_carries_no_administration_or_platform_authority(self) -> None:
        scopes = ROLE_SCOPES["demo"]
        assert not any(scope.startswith("admin:") for scope in scopes)
        assert not any(scope.startswith("platform:") for scope in scopes)
        # A demo session must never become a judge.
        assert not (scopes & JUDGE_PERMISSIONS)

    def test_it_carries_no_tenant_writes(self) -> None:
        writes = {s for s in ROLE_SCOPES["demo"] if s.endswith((":write", ":manage", ":approve"))}
        assert writes == set()

    def test_a_tenant_administrator_cannot_mint_one(self) -> None:
        assert "demo" not in TENANT_GRANTABLE_ROLES
        with pytest.raises(AuthError):
            assert_grantable(ROLE_SCOPES["owner"], "demo")

    def test_it_is_refused_when_bound_to_another_organization(self, make_client) -> None:  # type: ignore[no-untyped-def]
        # These routes only ever touch the demo organization, so a demo key issued for a different
        # one is refused rather than silently operating on demo data.
        from uuid import uuid4

        with _hosted_demo_client(make_client) as client:
            headers = _mint(client, "demo", uuid4())
            assert client.get("/demo/state", headers=headers).status_code == 403


class TestDemoAndJudgeCannotReachEachOther:
    def test_a_judge_credential_cannot_open_the_demo(self, make_client) -> None:  # type: ignore[no-untyped-def]
        with make_client(
            app_env="judge", auth_enabled=True, demo_enabled=True, judge_workspace_enabled=True
        ) as client:
            session = next(client.app.dependency_overrides.get(get_db, get_db)())
            provisioned = JudgeSandboxService(session, get_settings()).provision()
            session.commit()
            headers = {
                "X-DeceptiForge-API-Key": provisioned.api_key,
                "X-DeceptiForge-Org-Id": str(provisioned.namespace.organization_id),
            }
            assert client.get("/demo/state", headers=headers).status_code == 403

    def test_a_demo_credential_cannot_open_the_judge_workspace(self, make_client) -> None:  # type: ignore[no-untyped-def]
        with make_client(
            app_env="judge", auth_enabled=True, demo_enabled=True, judge_workspace_enabled=True
        ) as client:
            headers = _mint(client, "demo", DEMO_ORGANIZATION_ID)
            assert client.get("/api/v1/judge/workspace", headers=headers).status_code == 403

    def test_the_demo_writes_to_its_own_organization_only(self, make_client) -> None:  # type: ignore[no-untyped-def]
        # The demo drives DEMO_ORGANIZATION_ID; judge sandboxes get generated ids. Seeding the demo
        # must leave a judge's sandbox untouched.
        with make_client(
            app_env="judge", auth_enabled=True, demo_enabled=True, judge_workspace_enabled=True
        ) as client:
            session = next(client.app.dependency_overrides.get(get_db, get_db)())
            provisioned = JudgeSandboxService(session, get_settings()).provision()
            session.commit()
            judge_headers = {
                "X-DeceptiForge-API-Key": provisioned.api_key,
                "X-DeceptiForge-Org-Id": str(provisioned.namespace.organization_id),
            }
            before = client.get("/api/v1/judge/export", headers=judge_headers).json()

            client.post("/demo/seed", headers=_mint(client, "demo", DEMO_ORGANIZATION_ID))

            after = client.get("/api/v1/judge/export", headers=judge_headers).json()
            assert after == {**before, "exported_at": after["exported_at"], "quotas": after["quotas"]}
