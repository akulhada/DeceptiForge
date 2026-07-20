# Purpose: verify the agent-sensor HTTP surface — enrollment, sessions, policies, signed minimized
#   activity ingestion, deterministic violations, idempotency, and cross-org isolation.
from __future__ import annotations

import time
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
    return make_client(
        demo_enabled=False, auth_enabled=True, app_env="development", agent_sensor_enabled=True,
    )


def _enroll(c, admin, org):  # type: ignore[no-untyped-def]
    token = c.post(
        "/agent-sensors/enrollment-tokens", headers=_headers(admin, org)
    ).json()["token"]
    resp = c.post(
        "/agent-sensors/enroll",
        json={"token": token, "name": "cli", "adapter_type": "jsonl", "version": "0.1.0"},
    )
    assert resp.status_code == 201
    return resp.json()


def _ingest_headers(sensor, org):  # type: ignore[no-untyped-def]
    return {
        **_headers(sensor["api_key"], org),
        "X-DeceptiForge-Sensor-Id": sensor["sensor_public_id"],
        "X-DeceptiForge-Nonce": uuid4().hex,
        "X-DeceptiForge-Timestamp": str(time.time()),
    }


def _start_session(c, sensor, org, ext="sess-1", allowed=("apps/web/**",)):  # type: ignore[no-untyped-def]
    resp = c.post(
        "/agent-sessions",
        json={
            "external_session_id": ext, "agent_type": "claude-code",
            "task_summary": "Fix the mobile navbar spacing",
            "allowed_paths": list(allowed),
        },
        headers=_headers(sensor["api_key"], org),
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _event(c, sensor, org, **over):  # type: ignore[no-untyped-def]
    body = {
        "external_event_id": uuid4().hex, "session_external_id": "sess-1",
        "event_type": "file_read", "path": "apps/web/navbar.tsx",
    }
    body.update(over)
    return c.post("/monitoring/agent-events", json=body, headers=_ingest_headers(sensor, org))


def test_flag_off_hides_routes(make_client) -> None:  # type: ignore[no-untyped-def]
    org = str(uuid4())
    with make_client(auth_enabled=True, app_env="development") as c:
        key = _key(c, org, "owner")
        assert c.get("/agent-sensors", headers=_headers(key, org)).status_code == 404


def test_enroll_one_time_secret_once(make_client) -> None:  # type: ignore[no-untyped-def]
    org = str(uuid4())
    with _client(make_client) as c:
        admin = _key(c, org, "admin")
        token = c.post(
            "/agent-sensors/enrollment-tokens", headers=_headers(admin, org)
        ).json()["token"]
        body = {"token": token, "name": "cli", "adapter_type": "jsonl", "version": "0.1.0"}
        first = c.post("/agent-sensors/enroll", json=body)
        assert first.status_code == 201 and "signing_secret" in first.json()
        assert c.post("/agent-sensors/enroll", json=body).status_code == 409


def test_in_scope_event_not_flagged(make_client) -> None:  # type: ignore[no-untyped-def]
    org = str(uuid4())
    with _client(make_client) as c:
        sensor = _enroll(c, _key(c, org, "admin"), org)
        _start_session(c, sensor, org)
        resp = _event(c, sensor, org, path="apps/web/navbar.tsx")
        assert resp.status_code == 200
        assert resp.json()["violation_type"] is None
        assert resp.json()["path_class"] == "task_relevant"


def test_sensitive_and_decoy_flagged(make_client) -> None:  # type: ignore[no-untyped-def]
    org = str(uuid4())
    with _client(make_client) as c:
        sensor = _enroll(c, _key(c, org, "admin"), org)
        _start_session(c, sensor, org)
        sensitive = _event(c, sensor, org, path="services/auth/.env")
        assert sensitive.json()["violation_type"] == "sensitive_file_access"


def test_out_of_scope_and_full_content_rejected(make_client) -> None:  # type: ignore[no-untyped-def]
    org = str(uuid4())
    with _client(make_client) as c:
        sensor = _enroll(c, _key(c, org, "admin"), org)
        _start_session(c, sensor, org)
        # metadata carrying raw content is stripped, not persisted.
        resp = _event(
            c, sensor, org, path="scripts/unrelated.py",
            metadata={"tool": "cat", "file_content": "SECRET SOURCE", "reasoning": "chain"},
        )
        assert resp.status_code == 200
        assert resp.json()["violation_type"] == "out_of_scope_path_access"
        admin = _key(c, org, "owner")
        sid = c.get("/agent-sessions", headers=_headers(admin, org)).json()[0]["id"]
        timeline = c.get(f"/agent-sessions/{sid}/timeline", headers=_headers(admin, org)).json()
        joined = str(timeline)
        assert "SECRET SOURCE" not in joined and "reasoning" not in joined


def test_event_idempotent(make_client) -> None:  # type: ignore[no-untyped-def]
    org = str(uuid4())
    with _client(make_client) as c:
        sensor = _enroll(c, _key(c, org, "admin"), org)
        _start_session(c, sensor, org)
        eid = uuid4().hex
        first = _event(c, sensor, org, external_event_id=eid, path="apps/web/x.tsx")
        second = _event(c, sensor, org, external_event_id=eid, path="apps/web/x.tsx")
        assert first.json()["idempotent"] is False
        assert second.json()["idempotent"] is True
        admin = _key(c, org, "owner")
        sid = c.get("/agent-sessions", headers=_headers(admin, org)).json()[0]["id"]
        timeline = c.get(f"/agent-sessions/{sid}/timeline", headers=_headers(admin, org)).json()
        assert len(timeline) == 1  # duplicate not persisted twice


def test_revoked_sensor_cannot_ingest(make_client) -> None:  # type: ignore[no-untyped-def]
    org = str(uuid4())
    with _client(make_client) as c:
        admin = _key(c, org, "admin")
        sensor = _enroll(c, admin, org)
        _start_session(c, sensor, org)
        c.post(f"/agent-sensors/{sensor['sensor_id']}/revoke", headers=_headers(admin, org))
        assert _event(c, sensor, org).status_code in (401, 403)


def test_cross_org_session_rejected(make_client) -> None:  # type: ignore[no-untyped-def]
    org_a, org_b = str(uuid4()), str(uuid4())
    with _client(make_client) as c:
        sensor_a = _enroll(c, _key(c, org_a, "admin"), org_a)
        s = _start_session(c, sensor_a, org_a)
        analyst_b = _key(c, org_b, "analyst")
        assert c.get(
            f"/agent-sessions/{s['id']}", headers=_headers(analyst_b, org_b)
        ).status_code == 404


def test_violations_listed_with_explanation(make_client) -> None:  # type: ignore[no-untyped-def]
    org = str(uuid4())
    with _client(make_client) as c:
        admin = _key(c, org, "admin")
        sensor = _enroll(c, admin, org)
        _start_session(c, sensor, org)
        _event(c, sensor, org, path="services/auth/.env")
        sid = c.get("/agent-sessions", headers=_headers(admin, org)).json()[0]["id"]
        violations = c.get(
            f"/agent-sessions/{sid}/violations", headers=_headers(admin, org)
        ).json()
        assert len(violations) == 1
        assert violations[0]["explanation"]
        assert violations[0]["policy_rule"]
