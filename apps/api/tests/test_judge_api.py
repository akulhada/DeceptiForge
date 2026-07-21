# Purpose: the judge workspace over real HTTP — authorization, bounded input, quota responses.
# Service-level tests cover the rules; these prove the wiring actually enforces them on a request.
from __future__ import annotations

import pytest

from app.config.settings import get_settings
from app.dependencies import get_db
from app.services.judge_sandbox import JudgeSandboxService

_SIGNALS = {"languages": [{"name": "python", "confidence": 0.9}]}


def _judge_client(make_client):  # type: ignore[no-untyped-def]
    """A judge-mode client with one provisioned sandbox, returning the client and its headers."""
    return make_client(
        app_env="judge",
        auth_enabled=True,
        judge_workspace_enabled=True,
        demo_enabled=False,
    )


def _provision(client):  # type: ignore[no-untyped-def]
    """Provision a sandbox through the service, exactly as out-of-band provisioning would."""
    session = next(client.app.dependency_overrides.get(get_db, get_db)())
    provisioned = JudgeSandboxService(session, get_settings()).provision()
    session.commit()
    headers = {
        "X-DeceptiForge-API-Key": provisioned.api_key,
        "X-DeceptiForge-Org-Id": str(provisioned.namespace.organization_id),
    }
    return provisioned, headers


def test_workspace_requires_authentication(make_client) -> None:  # type: ignore[no-untyped-def]
    with _judge_client(make_client) as client:
        # No anonymous fallback: the workspace is not reachable without a credential.
        assert client.get("/api/v1/judge/workspace").status_code in (401, 403)


def test_workspace_returns_backend_state(make_client) -> None:  # type: ignore[no-untyped-def]
    with _judge_client(make_client) as client:
        provisioned, headers = _provision(client)
        response = client.get("/api/v1/judge/workspace", headers=headers)
        assert response.status_code == 200
        body = response.json()
        assert body["organization_id"] == str(provisioned.namespace.organization_id)
        assert body["environment"] == "judge"
        # Quotas come from the sandbox row, never from a hardcoded frontend default.
        assert body["quotas"]["analyze"]["remaining"] == get_settings().judge_max_analysis_runs
        assert body["scenarios"], "predefined scenarios must be offered"


def test_analysis_runs_and_spends_budget(make_client) -> None:  # type: ignore[no-untyped-def]
    with _judge_client(make_client) as client:
        _, headers = _provision(client)
        response = client.post(
            "/api/v1/judge/analyze", json={"signals": _SIGNALS}, headers=headers
        )
        assert response.status_code == 200
        after = client.get("/api/v1/judge/workspace", headers=headers).json()
        assert after["quotas"]["analyze"]["used"] == 1


@pytest.mark.parametrize(
    "payload",
    [
        {"signals": _SIGNALS, "path": "/etc/passwd"},
        {"signals": _SIGNALS, "repository_url": "https://github.com/acme/private.git"},
        {"signals": _SIGNALS, "command": "cat .env"},
        {"signals": _SIGNALS, "connector_token": "ghp_example"},
    ],
)
def test_unmodelled_fields_are_refused(make_client, payload: dict) -> None:  # type: ignore[no-untyped-def]
    # The contract forbids extras, so a path to scan, a repository URL, a shell command or a
    # credential cannot ride along inside an otherwise valid analysis request.
    with _judge_client(make_client) as client:
        _, headers = _provision(client)
        response = client.post("/api/v1/judge/analyze", json=payload, headers=headers)
        assert response.status_code == 422


def test_reset_clears_only_this_sandbox_and_then_rate_limits(make_client) -> None:  # type: ignore[no-untyped-def]
    with _judge_client(make_client) as client:
        _, headers = _provision(client)
        first = client.post("/api/v1/judge/reset", headers=headers)
        assert first.status_code == 200
        assert "deleted" in first.json()

        # Reset deletes and re-seeds, so it is paced. Here waiting genuinely helps, so the denial
        # must carry a Retry-After a client can act on.
        second = client.post("/api/v1/judge/reset", headers=headers)
        assert second.status_code == 429
        assert int(second.headers["Retry-After"]) > 0


def test_the_workspace_is_absent_in_production(make_client) -> None:  # type: ignore[no-untyped-def]
    with make_client(app_env="production", auth_enabled=True, demo_enabled=False) as client:
        assert client.get("/api/v1/judge/workspace").status_code == 404


def test_interaction_drives_the_real_pipeline(make_client) -> None:  # type: ignore[no-untyped-def]
    with _judge_client(make_client) as client:
        _, headers = _provision(client)

        before = client.get("/api/v1/judge/export", headers=headers).json()
        assert before["decoy_assets"] > 0, "the sandbox must start with predefined decoys"
        assert before["alerts"] == 0 and before["incidents"] == 0

        response = client.post("/api/v1/judge/interact", headers=headers)
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["event_recorded"] is True
        assert body["alert_id"], "the pipeline must have produced an alert"
        assert body["incident_id"], "reconstruction must have produced an incident"

        # Read back from persisted state, not from the interaction response: this proves the alert
        # and incident really exist rather than having been reported optimistically.
        after = client.get("/api/v1/judge/export", headers=headers).json()
        assert after["monitoring_events"] == before["monitoring_events"] + 1
        assert after["alerts"] == 1
        assert after["incidents"] >= 1


def test_the_interaction_endpoint_accepts_no_target(make_client) -> None:  # type: ignore[no-untyped-def]
    # The decoy is chosen server-side from the sandbox's own accepted assets. A judge supplying a
    # decoy id, organization or trace must not be able to aim the interaction anywhere.
    with _judge_client(make_client) as client:
        _, headers = _provision(client)
        response = client.post(
            "/api/v1/judge/interact",
            json={"decoy_plan_id": "00000000-0000-0000-0000-000000000001"},
            headers=headers,
        )
        # The body is ignored entirely; the interaction still targets this sandbox's own decoy.
        assert response.status_code == 200
        assert response.json()["alert_id"]


def test_export_carries_no_decoy_content_or_traces(make_client) -> None:  # type: ignore[no-untyped-def]
    # A judge must not walk away with material that would help defeat a real deployment.
    with _judge_client(make_client) as client:
        _, headers = _provision(client)
        client.post("/api/v1/judge/interact", headers=headers)
        body = client.get("/api/v1/judge/export", headers=headers).json()
        assert set(body) == {
            "organization_id",
            "session_id",
            "environment",
            "exported_at",
            "repositories",
            "decoy_assets",
            "monitoring_events",
            "alerts",
            "incidents",
            "quotas",
        }
        rendered = str(body)
        assert "trace" not in rendered.lower()


def test_interaction_and_export_spend_their_own_budgets(make_client) -> None:  # type: ignore[no-untyped-def]
    with _judge_client(make_client) as client:
        _, headers = _provision(client)
        client.post("/api/v1/judge/interact", headers=headers)
        client.get("/api/v1/judge/export", headers=headers)
        quotas = client.get("/api/v1/judge/workspace", headers=headers).json()["quotas"]
        assert quotas["interact"]["used"] == 1
        assert quotas["export"]["used"] == 1
        # Analysis is a separate budget and must be untouched by either.
        assert quotas["analyze"]["used"] == 0


def test_one_sandbox_cannot_see_another(make_client) -> None:  # type: ignore[no-untyped-def]
    with _judge_client(make_client) as client:
        mine, my_headers = _provision(client)
        _, their_headers = _provision(client)

        client.post("/api/v1/judge/interact", headers=my_headers)

        # The other judge's sandbox shows none of my activity.
        theirs = client.get("/api/v1/judge/export", headers=their_headers).json()
        assert theirs["alerts"] == 0
        assert theirs["incidents"] == 0

        # And presenting my key against their organization id is refused outright.
        crossed = client.get(
            "/api/v1/judge/workspace",
            headers={
                "X-DeceptiForge-API-Key": my_headers["X-DeceptiForge-API-Key"],
                "X-DeceptiForge-Org-Id": theirs["organization_id"],
            },
        )
        assert crossed.status_code in (401, 403)
        assert mine.namespace.organization_id != theirs["organization_id"]
