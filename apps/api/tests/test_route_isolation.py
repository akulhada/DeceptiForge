# Purpose: the cross-route isolation contract for the judge/demo/lab route model.
# Every test here answers one question: can a session on one route reach something belonging to
# another? A judge credential is handed to an untrusted third party in a hosted environment, so the
# interesting assertions are the negative ones.
from __future__ import annotations

from uuid import uuid4

import pytest

from app.config.constants import DEMO_ORGANIZATION_ID
from app.config.settings import get_settings
from app.dependencies import get_db
from app.services.api_keys import ApiKeyService
from app.services.judge_sandbox import JudgeSandboxService

# Signals that satisfy the contract, so a rejection below is about the boundary being tested and
# not about malformed input.
_SIGNALS = {"languages": [{"name": "python", "confidence": 0.9}]}


def _hosted(make_client, **overrides):  # type: ignore[no-untyped-def]
    """A judge-mode deployment hosting every surface a judge is allowed to see."""
    return make_client(
        app_env="judge",
        auth_enabled=True,
        demo_enabled=True,
        judge_workspace_enabled=True,
        **overrides,
    )


def _judge_headers(client):  # type: ignore[no-untyped-def]
    session = next(client.app.dependency_overrides.get(get_db, get_db)())
    provisioned = JudgeSandboxService(session, get_settings()).provision()
    session.commit()
    return provisioned, {
        "X-DeceptiForge-API-Key": provisioned.api_key,
        "X-DeceptiForge-Org-Id": str(provisioned.namespace.organization_id),
    }


def _mint(client, role: str, organization_id):  # type: ignore[no-untyped-def]
    session = next(client.app.dependency_overrides.get(get_db, get_db)())
    _, plaintext = ApiKeyService(session).create(organization_id, f"test-{role}", role)
    session.commit()
    return {
        "X-DeceptiForge-API-Key": plaintext,
        "X-DeceptiForge-Org-Id": str(organization_id),
    }


class TestJudgeCannotReachAdministration:
    """A judge workspace session must never become a tenant administrator."""

    @pytest.mark.parametrize(
        ("method", "path"),
        [
            ("get", "/admin/api-keys"),
            ("post", "/admin/api-keys"),
            ("get", "/admin/monitor-credentials"),
            ("post", "/admin/monitor-credentials"),
        ],
    )
    def test_tenant_administration_is_refused(self, make_client, method: str, path: str) -> None:  # type: ignore[no-untyped-def]
        with _hosted(make_client) as client:
            _, headers = _judge_headers(client)
            call = getattr(client, method)
            response = call(path, headers=headers) if method == "get" else call(
                path, headers=headers, json={}
            )
            # 403 (no scope) or 404 (router unmounted) — never a success. Minting keys is the
            # escalation that would matter most, so it is asserted explicitly above.
            assert response.status_code in (403, 404), response.text

    def test_a_judge_cannot_mint_itself_a_stronger_key(self, make_client) -> None:  # type: ignore[no-untyped-def]
        with _hosted(make_client) as client:
            _, headers = _judge_headers(client)
            response = client.post(
                "/admin/api-keys",
                headers=headers,
                json={"name": "escalation", "role": "owner"},
            )
            assert response.status_code in (403, 404)


class TestJudgeCannotReachPlatformOperations:
    """Platform scopes live outside every tenant role; a judge must not reach that plane."""

    @pytest.mark.parametrize(
        "path",
        [
            "/admin/reliability/status",
            "/admin/reliability/backups",
            "/admin/reliability/restore-drills",
        ],
    )
    def test_platform_routes_are_refused(self, make_client, path: str) -> None:  # type: ignore[no-untyped-def]
        with _hosted(make_client) as client:
            _, headers = _judge_headers(client)
            assert client.get(path, headers=headers).status_code in (403, 404)

    def test_production_connectors_are_unreachable(self, make_client) -> None:  # type: ignore[no-untyped-def]
        # Connector routers are not mounted in this configuration at all, so a judge cannot reach a
        # real integration even by guessing the path.
        with _hosted(make_client) as client:
            _, headers = _judge_headers(client)
            for path in ("/integrations", "/database-connectors", "/rag-connectors"):
                assert client.get(path, headers=headers).status_code in (403, 404)


class TestJudgeInputIsBounded:
    """Structured signals only: no paths opened, no size left unbounded."""

    def test_an_oversized_request_is_rejected(self, make_client) -> None:  # type: ignore[no-untyped-def]
        with _hosted(make_client) as client:
            _, headers = _judge_headers(client)
            # Far past the aggregate representative-path bound.
            payload = {
                "signals": {
                    "languages": [
                        {"name": f"lang-{i}", "representative_paths": [f"src/f{i}.py"]}
                        for i in range(500)
                    ]
                }
            }
            response = client.post("/api/v1/judge/analyze", json=payload, headers=headers)
            assert response.status_code in (413, 422)

    def test_a_path_like_value_is_never_opened(self, make_client, tmp_path) -> None:  # type: ignore[no-untyped-def]
        # Path-like values are descriptive metadata. Point one at a real file containing a marker
        # and assert the marker never appears in the response: if the backend had read it, the
        # analysis would be able to leak its contents.
        secret = tmp_path / "secret.txt"
        secret.write_text("MARKER-e7f1c2a9")
        with _hosted(make_client) as client:
            _, headers = _judge_headers(client)
            payload = {
                "signals": {
                    "languages": [{"name": "python", "representative_paths": [str(secret)]}]
                }
            }
            response = client.post("/api/v1/judge/analyze", json=payload, headers=headers)
            assert response.status_code == 200
            assert "MARKER-e7f1c2a9" not in response.text

    def test_a_scan_request_cannot_be_smuggled_in(self, make_client) -> None:  # type: ignore[no-untyped-def]
        with _hosted(make_client) as client:
            _, headers = _judge_headers(client)
            response = client.post(
                "/api/v1/judge/analyze",
                json={"signals": _SIGNALS, "scan_path": "/etc"},
                headers=headers,
            )
            assert response.status_code == 422

    def test_the_generic_scan_endpoint_stays_closed(self, make_client) -> None:  # type: ignore[no-untyped-def]
        # DEMO_ENABLED must not reopen arbitrary filesystem scanning in a hosted environment.
        with _hosted(make_client) as client:
            _, headers = _judge_headers(client)
            response = client.post(
                "/repositories/scan", json={"path": "/etc"}, headers=headers
            )
            assert response.status_code in (403, 404)


class TestDemoBoundary:
    """The curated demo is a fixed narrative: it takes no input and owns its own records."""

    def test_the_demo_accepts_no_arbitrary_input(self, make_client) -> None:  # type: ignore[no-untyped-def]
        # Every demo write is a parameterless command. A body is ignored rather than interpreted,
        # so there is no field through which a caller could steer the story.
        with _hosted(make_client) as client:
            headers = _mint(client, "demo", DEMO_ORGANIZATION_ID)
            hostile = {"path": "/etc/passwd", "repository_url": "https://example.invalid/x.git"}
            first = client.post("/demo/seed", headers=headers, json=hostile)
            assert first.status_code == 200
            # The seeded story is the bundled fixture, not anything the caller named.
            state = client.get("/demo/state").json()
            assert "etc/passwd" not in str(state)

    def test_demo_writes_do_not_touch_a_judge_sandbox(self, make_client) -> None:  # type: ignore[no-untyped-def]
        with _hosted(make_client) as client:
            _, judge_headers = _judge_headers(client)
            before = client.get("/api/v1/judge/export", headers=judge_headers).json()

            demo_headers = _mint(client, "demo", DEMO_ORGANIZATION_ID)
            client.post("/demo/seed", headers=demo_headers)
            client.post("/demo/reset", headers=demo_headers)

            after = client.get("/api/v1/judge/export", headers=judge_headers).json()
            fields = ("repositories", "decoy_assets", "monitoring_events", "alerts", "incidents")
            for field in fields:
                assert after[field] == before[field], f"demo reset changed the judge's {field}"

    def test_a_judge_reset_does_not_touch_demo_records(self, make_client) -> None:  # type: ignore[no-untyped-def]
        with _hosted(make_client) as client:
            demo_headers = _mint(client, "demo", DEMO_ORGANIZATION_ID)
            client.post("/demo/seed", headers=demo_headers)
            before = client.get("/demo/state").json()

            _, judge_headers = _judge_headers(client)
            assert client.post("/api/v1/judge/reset", headers=judge_headers).status_code == 200

            after = client.get("/demo/state").json()
            assert after["overview"] == before["overview"]


class TestClaimsDoNotEscalateBetweenRoutes:
    """A credential carries the same authority whichever route it is presented to."""

    def test_a_demo_credential_gains_nothing_on_the_judge_routes(self, make_client) -> None:  # type: ignore[no-untyped-def]
        with _hosted(make_client) as client:
            headers = _mint(client, "demo", DEMO_ORGANIZATION_ID)
            for path in ("/workspace", "/export"):
                assert client.get(f"/api/v1/judge{path}", headers=headers).status_code == 403
            for path in ("/analyze", "/interact", "/reset"):
                response = client.post(
                    f"/api/v1/judge{path}", headers=headers, json={"signals": _SIGNALS}
                )
                assert response.status_code == 403

    def test_a_judge_credential_gains_nothing_on_the_demo_routes(self, make_client) -> None:  # type: ignore[no-untyped-def]
        with _hosted(make_client) as client:
            _, headers = _judge_headers(client)
            for path in ("/demo/seed", "/demo/reset", "/demo/run"):
                assert client.post(path, headers=headers).status_code == 403

    def test_an_organization_header_cannot_override_the_credential(self, make_client) -> None:  # type: ignore[no-untyped-def]
        # The sandbox is resolved from the authenticated organization. Claiming another one in the
        # header must be refused rather than honoured.
        with _hosted(make_client) as client:
            provisioned, headers = _judge_headers(client)
            other, _ = _judge_headers(client)
            crossed = {
                **headers,
                "X-DeceptiForge-Org-Id": str(other.namespace.organization_id),
            }
            assert client.get("/api/v1/judge/workspace", headers=crossed).status_code in (401, 403)
            # And the honest header still works, proving the refusal was about the mismatch.
            assert client.get("/api/v1/judge/workspace", headers=headers).status_code == 200
            assert provisioned.namespace.organization_id != other.namespace.organization_id

    def test_an_unknown_organization_is_refused(self, make_client) -> None:  # type: ignore[no-untyped-def]
        with _hosted(make_client) as client:
            _, headers = _judge_headers(client)
            crossed = {**headers, "X-DeceptiForge-Org-Id": str(uuid4())}
            assert client.get("/api/v1/judge/workspace", headers=crossed).status_code in (401, 403)
