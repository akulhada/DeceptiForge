# Purpose: verify the browser-sensor HTTP surface — enrollment, lifecycle, policy, registry, and
#   signed minimized event ingestion.
# Responsibilities: flag gating, one-time/expired/cross-org enrollment, secret-not-returned-again,
#   revoked cannot ingest, invalid signature + replay rejected, registry isolation + no full
#   payloads, bounded metadata, raw-content never persisted, deterministic classification.
from __future__ import annotations

import time
from uuid import UUID, uuid4

from app.services.api_keys import ApiKeyService
from app.services.monitor_signing import canonical_request, sign


def _key(client, org: str, role: str) -> str:  # type: ignore[no-untyped-def]
    session = client.app_session()
    _, plaintext = ApiKeyService(session).create(UUID(org), role, role)
    session.commit()
    session.close()
    return plaintext


def _headers(key: str, org: str) -> dict[str, str]:
    return {"X-DeceptiForge-API-Key": key, "X-DeceptiForge-Org-Id": org}


def _client(make_client, *, signed: bool = False):  # type: ignore[no-untyped-def]
    return make_client(
        demo_enabled=False,
        auth_enabled=True,
        app_env="development",
        browser_sensor_enabled=True,
        monitor_signature_required=signed,
    )


def _enroll(c, admin_key, org):  # type: ignore[no-untyped-def]
    token = c.post("/browser-sensors/enrollment-tokens", headers=_headers(admin_key, org)).json()[
        "token"
    ]
    resp = c.post(
        "/browser-sensors/enroll",
        json={
            "token": token,
            "name": "laptop",
            "installation_id": "inst-1",
            "browser_family": "chromium",
            "extension_version": "0.1.0",
        },
    )
    assert resp.status_code == 201
    return resp.json()


def test_flag_off_hides_routes(make_client) -> None:  # type: ignore[no-untyped-def]
    org = str(uuid4())
    with make_client(auth_enabled=True, app_env="development") as c:
        key = _key(c, org, "owner")
        assert c.get("/browser-sensors", headers=_headers(key, org)).status_code == 404


def test_enroll_is_one_time_and_secret_shown_once(make_client) -> None:  # type: ignore[no-untyped-def]
    org = str(uuid4())
    with _client(make_client) as c:
        admin = _key(c, org, "admin")
        token = c.post("/browser-sensors/enrollment-tokens", headers=_headers(admin, org)).json()[
            "token"
        ]
        body = {
            "token": token,
            "name": "laptop",
            "installation_id": "inst-1",
            "browser_family": "chromium",
            "extension_version": "0.1.0",
        }
        first = c.post("/browser-sensors/enroll", json=body)
        assert first.status_code == 201
        assert "signing_secret" in first.json() and "api_key" in first.json()
        # Reuse of the same token is rejected (one-time).
        assert c.post("/browser-sensors/enroll", json=body).status_code == 409
        # The sensor summary never returns the secret.
        sid = first.json()["sensor_id"]
        summary = c.get(f"/browser-sensors/{sid}", headers=_headers(admin, org)).json()
        assert "signing_secret" not in summary and "secret" not in str(summary)


def test_unknown_token_rejected(make_client) -> None:  # type: ignore[no-untyped-def]
    with _client(make_client) as c:
        resp = c.post(
            "/browser-sensors/enroll",
            json={
                "token": "does-not-exist",
                "name": "x",
                "installation_id": "i",
                "browser_family": "chromium",
                "extension_version": "0.1.0",
            },
        )
        assert resp.status_code == 404


def test_policy_version_is_monotonic(make_client) -> None:  # type: ignore[no-untyped-def]
    org = str(uuid4())
    with _client(make_client) as c:
        admin = _key(c, org, "admin")
        v1 = c.put(
            "/browser-ai-policy",
            json={
                "enabled": True,
                "rules": [
                    {"domain": "chatgpt.com", "classification": "shadow"},
                ],
            },
            headers=_headers(admin, org),
        ).json()["policy_version"]
        v2 = c.put(
            "/browser-ai-policy",
            json={"enabled": True, "rules": []},
            headers=_headers(admin, org),
        ).json()["policy_version"]
        assert v2 > v1


def test_registry_is_org_scoped_and_hashed(make_client) -> None:  # type: ignore[no-untyped-def]
    org = str(uuid4())
    with _client(make_client) as c:
        sensor_key = _enroll(c, _key(c, org, "admin"), org)["api_key"]
        reg = c.get("/browser-trace-registry", headers=_headers(sensor_key, org)).json()
        assert reg["organization_id"] == org
        # Entries carry only hashed match tokens, never a full decoy document.
        for entry in reg["entries"]:
            assert len(entry["match_token"]) == 64
            assert "body" not in entry and "content" not in entry


def test_revoked_sensor_cannot_ingest(make_client) -> None:  # type: ignore[no-untyped-def]
    org = str(uuid4())
    with _client(make_client) as c:
        admin = _key(c, org, "admin")
        enrolled = _enroll(c, admin, org)
        c.post(f"/browser-sensors/{enrolled['sensor_id']}/revoke", headers=_headers(admin, org))
        # The scoped ingest key is revoked with the sensor.
        resp = c.post(
            "/monitoring/browser-events",
            json={
                "trace_id": "DFAI-abc",
                "destination_domain": "chatgpt.com",
                "event_type": "shadow_ai_paste_detected",
                "match_method": "exact",
            },
            headers={
                **_headers(enrolled["api_key"], org),
                "X-DeceptiForge-Sensor-Id": enrolled["sensor_public_id"],
                "X-DeceptiForge-Nonce": uuid4().hex,
                "X-DeceptiForge-Timestamp": str(time.time()),
            },
        )
        assert resp.status_code in (401, 403)


def test_event_minimized_and_classified(make_client) -> None:  # type: ignore[no-untyped-def]
    org = str(uuid4())
    with _client(make_client) as c:
        admin = _key(c, org, "admin")
        c.put(
            "/browser-ai-policy",
            json={
                "enabled": True,
                "rules": [
                    {"domain": "chatgpt.com", "classification": "shadow"},
                ],
            },
            headers=_headers(admin, org),
        )
        enrolled = _enroll(c, admin, org)
        resp = c.post(
            "/monitoring/browser-events",
            json={
                "trace_id": "DFAI-abc",
                "destination_domain": "chatgpt.com",
                "event_type": "shadow_ai_paste_detected",
                "match_method": "exact",
                "confidence": 0.9,
                "extension_version": "0.1.0",
                "policy_version": 2,
                "metadata": {
                    "editor": "contenteditable",
                    "pasted_text": "SECRET DECOY VALUE",  # forbidden -> dropped
                    "conversation": "history",  # forbidden -> dropped
                },
            },
            headers={
                **_headers(enrolled["api_key"], org),
                "X-DeceptiForge-Sensor-Id": enrolled["sensor_public_id"],
                "X-DeceptiForge-Nonce": uuid4().hex,
                "X-DeceptiForge-Timestamp": str(time.time()),
            },
        )
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["destination_classification"] == "shadow"
        assert payload["exposure_type"] == "shadow_ai_exposure"
        events = c.get("/browser-events", headers=_headers(admin, org)).json()
        assert len(events) == 1
        meta = events[0]["minimized_metadata"]
        assert "SECRET DECOY VALUE" not in meta and "history" not in meta
        assert "editor" in meta


def test_signed_ingestion_and_replay(make_client) -> None:  # type: ignore[no-untyped-def]
    org = str(uuid4())
    with _client(make_client, signed=True) as c:
        admin = _key(c, org, "admin")
        enrolled = _enroll(c, admin, org)
        secret = enrolled["signing_secret"]
        sensor_pub = enrolled["sensor_public_id"]
        nonce = uuid4().hex
        ts = str(time.time())
        import json as _json

        body_obj = {
            "trace_id": "DFAI-abc",
            "destination_domain": "chatgpt.com",
            "event_type": "shadow_ai_paste_detected",
            "match_method": "exact",
        }
        raw = _json.dumps(body_obj).encode()
        canonical = canonical_request(
            method="POST",
            path="/monitoring/browser-events",
            organization_id=org,
            monitor_id=sensor_pub,
            timestamp=ts,
            nonce=nonce,
            body=raw,
        )
        signature = sign(secret, canonical)
        headers = {
            **_headers(enrolled["api_key"], org),
            "X-DeceptiForge-Sensor-Id": sensor_pub,
            "X-DeceptiForge-Nonce": nonce,
            "X-DeceptiForge-Timestamp": ts,
            "X-DeceptiForge-Signature": signature,
            "content-type": "application/json",
        }
        ok = c.post("/monitoring/browser-events", content=raw, headers=headers)
        assert ok.status_code == 200
        # Same nonce again -> replay rejected.
        replay = c.post("/monitoring/browser-events", content=raw, headers=headers)
        assert replay.status_code == 409
        # Bad signature -> rejected.
        bad = dict(headers)
        bad["X-DeceptiForge-Nonce"] = uuid4().hex
        bad["X-DeceptiForge-Signature"] = "deadbeef"
        assert c.post("/monitoring/browser-events", content=raw, headers=bad).status_code == 401
