# Purpose: verify the production boundary: auth stub, organization scoping, and narrative revisions.
# Responsibilities: prove missing/cross-org access is rejected, revisions append (not overwrite),
#   matching context is reused unless forced, and incident data is never mutated by narrative work.
# Dependencies: the make_client factory and the client fixture.
from __future__ import annotations

from uuid import uuid4

from app.config.constants import DEMO_ORGANIZATION_ID

_KEY = "local-development-key"
_AUTH = {"X-DeceptiForge-API-Key": _KEY, "X-DeceptiForge-Org-Id": str(DEMO_ORGANIZATION_ID)}


def _seed_incident(client) -> str:
    client.post("/demo/seed")
    return client.post("/demo/simulate-detection").json()["incidents"][0]["incident_id"]


def test_missing_auth_rejected_when_enabled(make_client) -> None:
    with make_client(demo_enabled=True, auth_enabled=True, app_env="development") as client:
        incident_id = _seed_incident(client)
        assert client.post(f"/incidents/{incident_id}/narrative").status_code == 401
        assert client.post(f"/incidents/{incident_id}/narrative", headers=_AUTH).status_code == 200


def test_auth_bypass_is_rejected_outside_development(make_client) -> None:
    """Production refuses to start with authentication disabled, so the bypass is unreachable."""
    import pytest

    with pytest.raises(RuntimeError, match="AUTH_ENABLED"):
        with make_client(demo_enabled=True, auth_enabled=False, app_env="production"):
            pass


def test_cross_org_incident_access_rejected(make_client) -> None:
    with make_client(demo_enabled=True, auth_enabled=True, app_env="development") as client:
        incident_id = _seed_incident(client)
        foreign = {"X-DeceptiForge-API-Key": _KEY, "X-DeceptiForge-Org-Id": str(uuid4())}
        assert (
            client.post(f"/incidents/{incident_id}/narrative", headers=foreign).status_code == 404
        )
        assert client.get(f"/incidents/{incident_id}/narrative", headers=foreign).status_code == 404
        assert client.get("/incidents", headers=foreign).status_code == 200
        assert client.get("/incidents", headers=foreign).json()["incidents"] == []


def test_force_regeneration_appends_revisions(client) -> None:
    incident_id = _seed_incident(client)

    first = client.post(f"/incidents/{incident_id}/narrative", params={"force": True}).json()
    second = client.post(f"/incidents/{incident_id}/narrative", params={"force": True}).json()

    assert first["revision_number"] == 1
    assert second["revision_number"] == 2
    history = client.get(f"/incidents/{incident_id}/narratives").json()
    assert [item["revision_number"] for item in history] == [1, 2]


def test_matching_context_is_reused_without_force(client) -> None:
    incident_id = _seed_incident(client)

    first = client.post(f"/incidents/{incident_id}/narrative").json()
    reused = client.post(f"/incidents/{incident_id}/narrative").json()

    # Same context within the cooldown returns the existing revision instead of creating a new one.
    assert reused["revision_number"] == first["revision_number"] == 1
    assert len(client.get(f"/incidents/{incident_id}/narratives").json()) == 1


def test_narrative_generation_does_not_mutate_incident(client) -> None:
    incident_id = _seed_incident(client)
    before = next(
        item
        for item in client.get("/demo/state").json()["incidents"]
        if item["incident_id"] == incident_id
    )

    client.post(f"/incidents/{incident_id}/narrative", params={"force": True})

    after = next(
        item
        for item in client.get("/demo/state").json()["incidents"]
        if item["incident_id"] == incident_id
    )
    assert before == after
