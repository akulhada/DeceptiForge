# Purpose: verify monitor-signature-v1 canonicalization and end-to-end signed ingestion.
# Responsibilities: exercise the canonical payload, constant-time verification, and the ingestion
#   gate for valid signatures, tampered body/path/organization/monitor-id, malformed/invalid
#   signatures, revoked and cross-organization credentials, replayed nonces, and expired timestamps.
# Dependencies: the test client factory, MonitorCredentialService, and the signing helpers.
from __future__ import annotations

import json
import time
from uuid import UUID, uuid4

from app.config.settings import get_settings
from app.services.api_keys import ApiKeyService
from app.services.monitor_credentials import MonitorCredentialService
from app.services.monitor_signing import canonical_request, sign, verify

_PATH = "/monitoring/events"


# ---- unit: canonicalization + verification -------------------------------------------------------


def test_canonical_request_is_stable_and_versioned() -> None:
    payload = canonical_request(
        method="post",
        path="/monitoring/events",
        organization_id="org",
        monitor_id="dfm_1",
        timestamp="1000",
        nonce="n1",
        body=b'{"a":1}',
    )
    lines = payload.split("\n")
    assert lines[0] == "monitor-signature-v1"
    assert lines[1] == "POST"  # method normalized to uppercase
    assert lines[2] == "/monitoring/events"
    assert lines[3:7] == ["org", "dfm_1", "1000", "n1"]
    assert len(lines[7]) == 64  # body sha-256 hex


def test_verify_accepts_matching_and_rejects_tampered() -> None:
    canonical = canonical_request(
        method="POST",
        path=_PATH,
        organization_id="org",
        monitor_id="dfm_1",
        timestamp="1000",
        nonce="n1",
        body=b"body",
    )
    signature = sign("secret", canonical)
    assert verify("secret", canonical, signature) is True
    assert verify("secret", canonical, "deadbeef") is False
    assert verify("wrong-secret", canonical, signature) is False


# ---- end-to-end signed ingestion -----------------------------------------------------------------


def _seed_service_key(client, org: str) -> str:  # type: ignore[no-untyped-def]
    session = client.app_session()
    _, plaintext = ApiKeyService(session).create(UUID(org), "svc", "service")
    session.commit()
    session.close()
    return plaintext


def _seed_monitor(client, org: str) -> tuple[str, str]:  # type: ignore[no-untyped-def]
    session = client.app_session()
    record, secret = MonitorCredentialService(session, get_settings()).create(UUID(org), "m")
    monitor_id = record.monitor_id
    session.commit()
    session.close()
    return monitor_id, secret


def _signed_headers(
    *,
    api_key: str,
    org: str,
    monitor_id: str,
    secret: str,
    body: bytes,
    nonce: str,
    timestamp: str | None = None,
    sign_org: str | None = None,
    sign_path: str = _PATH,
    sign_monitor: str | None = None,
) -> dict[str, str]:
    timestamp = timestamp or str(int(time.time()))
    canonical = canonical_request(
        method="POST",
        path=sign_path,
        organization_id=sign_org or org,
        monitor_id=sign_monitor or monitor_id,
        timestamp=timestamp,
        nonce=nonce,
        body=body,
    )
    return {
        "Content-Type": "application/json",
        "X-DeceptiForge-API-Key": api_key,
        "X-DeceptiForge-Org-Id": org,
        "X-DeceptiForge-Monitor-ID": monitor_id,
        "X-DeceptiForge-Timestamp": timestamp,
        "X-DeceptiForge-Nonce": nonce,
        "X-DeceptiForge-Signature": sign(secret, canonical),
    }


def _body(decoy_plan_id: str | None = None) -> bytes:
    payload = {
        "decoy_plan_id": decoy_plan_id or str(uuid4()),
        "surface": "repository",
        "location": "x",
        "value": "y",
    }
    return json.dumps(payload).encode("utf-8")


def _client(make_client):  # type: ignore[no-untyped-def]
    return make_client(
        demo_enabled=False,
        auth_enabled=True,
        app_env="production",
        monitor_signature_required=True,
    )


def test_valid_signature_reaches_pipeline(make_client) -> None:  # type: ignore[no-untyped-def]
    org = str(uuid4())
    with _client(make_client) as client:
        key = _seed_service_key(client, org)
        monitor_id, secret = _seed_monitor(client, org)
        body = _body()
        headers = _signed_headers(
            api_key=key, org=org, monitor_id=monitor_id, secret=secret, body=body, nonce="ok1"
        )
        response = client.post(_PATH, content=body, headers=headers)
        # Signature valid: passes the gate; the random decoy plan is missing -> 409, not 401.
        assert response.status_code == 409
        assert response.json()["detail"] != "invalid monitor signature"


def test_missing_signature_headers_rejected(make_client) -> None:  # type: ignore[no-untyped-def]
    org = str(uuid4())
    with _client(make_client) as client:
        key = _seed_service_key(client, org)
        _seed_monitor(client, org)
        body = _body()
        headers = {
            "Content-Type": "application/json",
            "X-DeceptiForge-API-Key": key,
            "X-DeceptiForge-Org-Id": org,
        }
        assert client.post(_PATH, content=body, headers=headers).status_code == 401


def test_modified_body_rejected(make_client) -> None:  # type: ignore[no-untyped-def]
    org = str(uuid4())
    with _client(make_client) as client:
        key = _seed_service_key(client, org)
        monitor_id, secret = _seed_monitor(client, org)
        signed_body = _body()
        headers = _signed_headers(
            api_key=key, org=org, monitor_id=monitor_id, secret=secret, body=signed_body, nonce="b1"
        )
        tampered = _body()  # different bytes than were signed
        response = client.post(_PATH, content=tampered, headers=headers)
        assert response.status_code == 401
        assert response.json()["detail"] == "invalid monitor signature"


def test_modified_path_rejected(make_client) -> None:  # type: ignore[no-untyped-def]
    org = str(uuid4())
    with _client(make_client) as client:
        key = _seed_service_key(client, org)
        monitor_id, secret = _seed_monitor(client, org)
        body = _body()
        headers = _signed_headers(
            api_key=key,
            org=org,
            monitor_id=monitor_id,
            secret=secret,
            body=body,
            nonce="p1",
            sign_path="/monitoring/other",
        )
        assert client.post(_PATH, content=body, headers=headers).status_code == 401


def test_modified_organization_rejected(make_client) -> None:  # type: ignore[no-untyped-def]
    org = str(uuid4())
    with _client(make_client) as client:
        key = _seed_service_key(client, org)
        monitor_id, secret = _seed_monitor(client, org)
        body = _body()
        headers = _signed_headers(
            api_key=key,
            org=org,
            monitor_id=monitor_id,
            secret=secret,
            body=body,
            nonce="o1",
            sign_org=str(uuid4()),  # signed with a different organization id
        )
        assert client.post(_PATH, content=body, headers=headers).status_code == 401


def test_modified_monitor_id_rejected(make_client) -> None:  # type: ignore[no-untyped-def]
    org = str(uuid4())
    with _client(make_client) as client:
        key = _seed_service_key(client, org)
        monitor_id, secret = _seed_monitor(client, org)
        body = _body()
        headers = _signed_headers(
            api_key=key,
            org=org,
            monitor_id=monitor_id,
            secret=secret,
            body=body,
            nonce="m1",
            sign_monitor="dfm_tampered",  # signature computed for a different monitor id
        )
        assert client.post(_PATH, content=body, headers=headers).status_code == 401


def test_malformed_signature_rejected(make_client) -> None:  # type: ignore[no-untyped-def]
    org = str(uuid4())
    with _client(make_client) as client:
        key = _seed_service_key(client, org)
        monitor_id, _secret = _seed_monitor(client, org)
        body = _body()
        headers = {
            "Content-Type": "application/json",
            "X-DeceptiForge-API-Key": key,
            "X-DeceptiForge-Org-Id": org,
            "X-DeceptiForge-Monitor-ID": monitor_id,
            "X-DeceptiForge-Timestamp": str(int(time.time())),
            "X-DeceptiForge-Nonce": "z1",
            "X-DeceptiForge-Signature": "not-a-real-signature",
        }
        assert client.post(_PATH, content=body, headers=headers).status_code == 401


def test_revoked_credential_rejected(make_client) -> None:  # type: ignore[no-untyped-def]
    org = str(uuid4())
    with _client(make_client) as client:
        key = _seed_service_key(client, org)
        monitor_id, secret = _seed_monitor(client, org)
        # Revoke the credential.
        session = client.app_session()
        service = MonitorCredentialService(session, get_settings())
        (record,) = service.list(UUID(org))
        service.revoke(UUID(org), record.id)
        session.commit()
        session.close()
        body = _body()
        headers = _signed_headers(
            api_key=key, org=org, monitor_id=monitor_id, secret=secret, body=body, nonce="r1"
        )
        assert client.post(_PATH, content=body, headers=headers).status_code == 401


def test_cross_organization_credential_rejected(make_client) -> None:  # type: ignore[no-untyped-def]
    org_a, org_b = str(uuid4()), str(uuid4())
    with _client(make_client) as client:
        key_a = _seed_service_key(client, org_a)
        monitor_b, secret_b = _seed_monitor(client, org_b)  # credential belongs to org B
        body = _body()
        # Authenticate as org A but present org B's monitor credential.
        headers = _signed_headers(
            api_key=key_a, org=org_a, monitor_id=monitor_b, secret=secret_b, body=body, nonce="x1"
        )
        assert client.post(_PATH, content=body, headers=headers).status_code == 403


def test_replayed_nonce_rejected(make_client) -> None:  # type: ignore[no-untyped-def]
    org = str(uuid4())
    with _client(make_client) as client:
        key = _seed_service_key(client, org)
        monitor_id, secret = _seed_monitor(client, org)
        body = _body()
        headers = _signed_headers(
            api_key=key, org=org, monitor_id=monitor_id, secret=secret, body=body, nonce="dup"
        )
        client.post(_PATH, content=body, headers=headers)  # first use reserves the nonce
        replay = client.post(_PATH, content=body, headers=headers)
        assert replay.status_code == 409
        assert replay.json()["detail"] == "replayed nonce"


def test_expired_timestamp_rejected(make_client) -> None:  # type: ignore[no-untyped-def]
    org = str(uuid4())
    with _client(make_client) as client:
        key = _seed_service_key(client, org)
        monitor_id, secret = _seed_monitor(client, org)
        body = _body()
        headers = _signed_headers(
            api_key=key,
            org=org,
            monitor_id=monitor_id,
            secret=secret,
            body=body,
            nonce="old",
            timestamp="1",  # far outside the skew window
        )
        response = client.post(_PATH, content=body, headers=headers)
        assert response.status_code == 400
        assert response.json()["detail"] == "timestamp outside the allowed clock skew"


# ---- admin monitor-credential endpoints ----------------------------------------------------------


def _seed_owner(client, org: str) -> str:  # type: ignore[no-untyped-def]
    session = client.app_session()
    _, plaintext = ApiKeyService(session).create(UUID(org), "owner", "owner")
    session.commit()
    session.close()
    return plaintext


def test_admin_can_manage_monitor_credentials(make_client) -> None:  # type: ignore[no-untyped-def]
    org = str(uuid4())
    with make_client(demo_enabled=False, auth_enabled=True, app_env="production") as client:
        owner = _seed_owner(client, org)
        headers = {"X-DeceptiForge-API-Key": owner, "X-DeceptiForge-Org-Id": org}
        created = client.post(
            "/admin/monitor-credentials", json={"name": "edge-1"}, headers=headers
        )
        assert created.status_code == 200
        payload = created.json()
        assert payload["signing_secret"] and payload["monitor_id"].startswith("dfm_")

        listed = client.get("/admin/monitor-credentials", headers=headers)
        assert listed.status_code == 200
        rows = listed.json()
        assert len(rows) == 1
        # The list view must never expose the secret material.
        assert "signing_secret" not in rows[0] and "secret_ciphertext" not in rows[0]

        credential_id = rows[0]["id"]
        assert (
            client.delete(
                f"/admin/monitor-credentials/{credential_id}", headers=headers
            ).status_code
            == 204
        )


def test_viewer_cannot_manage_monitor_credentials(make_client) -> None:  # type: ignore[no-untyped-def]
    org = str(uuid4())
    with make_client(demo_enabled=False, auth_enabled=True, app_env="production") as client:
        session = client.app_session()
        _, viewer = ApiKeyService(session).create(UUID(org), "v", "viewer")
        session.commit()
        session.close()
        headers = {"X-DeceptiForge-API-Key": viewer, "X-DeceptiForge-Org-Id": org}
        assert (
            client.post(
                "/admin/monitor-credentials", json={"name": "x"}, headers=headers
            ).status_code
            == 403
        )
