# Purpose: verify the reliability admin surface — status/dependencies/backups, restore drill,
#   failover request/approve with separation of duties, unauthorized failover rejection, and that
#   failback cannot start before recovery validation.
from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.services.api_keys import ApiKeyService


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


def test_status_and_dependencies(make_client) -> None:  # type: ignore[no-untyped-def]
    org = str(uuid4())
    with _client(make_client) as c:
        key = _key(c, org, "owner")
        status = c.get("/admin/reliability/status", headers=_headers(key, org)).json()
        assert status["failover_state"] == "normal"
        assert status["region"]["role"] == "primary"
        deps = c.get("/admin/reliability/dependencies", headers=_headers(key, org)).json()
        assert deps["database"]["status"] == "ok"


def test_backups_never_leak_secrets(make_client) -> None:  # type: ignore[no-untyped-def]
    org = str(uuid4())
    with _client(make_client) as c:
        key = _key(c, org, "owner")
        meta = c.get("/admin/reliability/backups", headers=_headers(key, org)).json()
        # Table names allowed; no secret *values*.
        assert "migration_revision" in meta
        assert '"secret":' not in str(meta)


def test_reliability_read_requires_scope(make_client) -> None:  # type: ignore[no-untyped-def]
    org = str(uuid4())
    with _client(make_client) as c:
        # A key with no reliability scope cannot request failover.
        analyst = _key(c, org, "analyst")
        resp = c.post(
            "/admin/reliability/failover/request", json={"reason": "x"},
            headers=_headers(analyst, org),
        )
        assert resp.status_code == 403


def test_failover_request_then_approve_sod(make_client) -> None:  # type: ignore[no-untyped-def]
    org = str(uuid4())
    with _client(make_client) as c:
        owner = _key(c, org, "owner")  # owner has both request + approve scopes
        req = c.post(
            "/admin/reliability/failover/request", json={"reason": "region outage"},
            headers=_headers(owner, org),
        )
        assert req.status_code == 200 and req.json()["failover_state"] == "failover_requested"
        # Same actor cannot approve their own request (separation of duties).
        same = c.post(
            "/admin/reliability/failover/approve", json={"reason": "approve"},
            headers=_headers(owner, org),
        )
        assert same.status_code == 403
        # A separate operator approves -> primary fenced.
        owner2 = _key(c, org, "owner")
        ok = c.post(
            "/admin/reliability/failover/approve", json={"reason": "approve"},
            headers=_headers(owner2, org),
        )
        assert ok.status_code == 200 and ok.json()["failover_state"] == "primary_fenced"


def test_failback_cannot_start_before_recovery_validation(make_client) -> None:  # type: ignore[no-untyped-def]
    org = str(uuid4())
    with _client(make_client) as c:
        owner = _key(c, org, "owner")
        # Jumping straight to failback_pending from normal is an illegal transition.
        resp = c.post(
            "/admin/reliability/failover/advance",
            json={"target": "failback_pending", "reason": "x"}, headers=_headers(owner, org),
        )
        assert resp.status_code == 409


def test_restore_drill_gated_and_runs(make_client) -> None:  # type: ignore[no-untyped-def]
    org = str(uuid4())
    # Disabled by default -> 404.
    with _client(make_client) as c:
        key = _key(c, org, "owner")
        assert c.post(
            "/admin/reliability/restore-drills",
            json={"backup_identifier": "b", "recovery_point": datetime.now(UTC).isoformat()},
            headers=_headers(key, org),
        ).status_code == 404
    # Enabled -> runs and records a drill with checks + RPO/RTO.
    with make_client(
        demo_enabled=False, auth_enabled=True, app_env="development",
    ) as c:
        import os

        os.environ["RESTORE_DRILL_ENABLED"] = "true"
        from app.config.settings import get_settings

        get_settings.cache_clear()
        key = _key(c, org, "owner")
        resp = c.post(
            "/admin/reliability/restore-drills",
            json={"backup_identifier": "b", "recovery_point": datetime.now(UTC).isoformat()},
            headers=_headers(key, org),
        )
        os.environ.pop("RESTORE_DRILL_ENABLED", None)
        get_settings.cache_clear()
        assert resp.status_code == 200
        assert "achieved_rpo_minutes" in resp.json() and resp.json()["checks"]
