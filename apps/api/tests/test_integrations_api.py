# Purpose: verify the integrations HTTP surface — flag gating, SSRF-rejected create, secret never
#   returned, test connection (synthetic), cross-org isolation, delivery listing + retry, and manual
#   incident export formats.
from __future__ import annotations

from uuid import UUID, uuid4

from app.models.records import IncidentRecord
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
        demo_enabled=False,
        auth_enabled=True,
        app_env="development",
        security_integrations_enabled=True,
    )


def _create(c, key, org, endpoint="https://93.184.216.34/hook"):  # type: ignore[no-untyped-def]
    return c.post(
        "/security-integrations",
        json={
            "integration_type": "generic_webhook",
            "name": "siem",
            "endpoint": endpoint,
            "secret": "signing-secret",
            "minimum_severity": "low",
            "payload_profile": "standard",
        },
        headers=_headers(key, org),
    )


def test_flag_off_hides_routes(make_client) -> None:  # type: ignore[no-untyped-def]
    org = str(uuid4())
    with make_client(auth_enabled=True, app_env="development") as c:
        key = _key(c, org, "owner")
        assert c.get("/security-integrations", headers=_headers(key, org)).status_code == 404


def test_create_rejects_ssrf_and_hides_secret(make_client) -> None:  # type: ignore[no-untyped-def]
    org = str(uuid4())
    with _client(make_client) as c:
        admin = _key(c, org, "admin")
        # Loopback endpoint is rejected before persistence.
        bad = _create(c, admin, org, endpoint="https://127.0.0.1/hook")
        assert bad.status_code == 400
        ok = _create(c, admin, org, endpoint="https://93.184.216.34/hook")
        assert ok.status_code == 201
        assert "signing-secret" not in ok.text
        listing = c.get("/security-integrations", headers=_headers(admin, org)).json()
        assert "signing-secret" not in str(listing)


def test_test_connection_uses_fake_transport(make_client, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from app.services.integrations.adapter import HttpResponse

    class FakeTransport:
        def send(self, request, *, timeout):  # type: ignore[no-untyped-def]
            return HttpResponse(status=200, headers={})

    monkeypatch.setattr("app.api.integrations.build_http_transport", lambda: FakeTransport())
    org = str(uuid4())
    with _client(make_client) as c:
        admin = _key(c, org, "admin")
        iid = _create(c, admin, org).json()["id"]
        resp = c.post(f"/security-integrations/{iid}/test", headers=_headers(admin, org))
        assert resp.status_code == 200 and resp.json()["ok"] is True


def test_cross_org_integration_isolation(make_client) -> None:  # type: ignore[no-untyped-def]
    org_a, org_b = str(uuid4()), str(uuid4())
    with _client(make_client) as c:
        admin_a = _key(c, org_a, "admin")
        iid = _create(c, admin_a, org_a).json()["id"]
        admin_b = _key(c, org_b, "admin")
        assert (
            c.post(
                f"/security-integrations/{iid}/disable", headers=_headers(admin_b, org_b)
            ).status_code
            == 404
        )
        assert c.get("/security-integrations", headers=_headers(admin_b, org_b)).json() == []


def test_manual_incident_export_formats(make_client) -> None:  # type: ignore[no-untyped-def]
    import json as _json

    org = str(uuid4())
    with _client(make_client) as c:
        analyst = _key(c, org, "analyst")
        session = c.app_session()
        incident = IncidentRecord(
            id=uuid4(),
            organization_id=UUID(org),
            status="open",
            data=_json.dumps(
                {
                    "title": "Decoy touched",
                    "summary": "a repository decoy was accessed",
                    "severity": "high",
                    "affected_surfaces": ["repository"],
                }
            ),
        )
        session.add(incident)
        session.commit()
        iid = str(incident.id)
        session.close()
        j = c.get(f"/security-export/incidents/{iid}?format=json", headers=_headers(analyst, org))
        assert j.status_code == 200 and "Decoy touched" in j.text
        md = c.get(
            f"/security-export/incidents/{iid}?format=markdown", headers=_headers(analyst, org)
        )
        assert md.status_code == 200 and md.text.startswith("# DeceptiForge incident report")
        stix = c.get(
            f"/security-export/incidents/{iid}?format=stix", headers=_headers(analyst, org)
        ).json()
        assert stix["type"] == "bundle"
        # Synthetic decoy is never a malicious Indicator.
        assert all(o["type"] != "indicator" for o in stix["objects"])
        assert (
            c.get(
                f"/security-export/incidents/{iid}?format=bogus", headers=_headers(analyst, org)
            ).status_code
            == 400
        )


def test_export_permission_enforced(make_client) -> None:  # type: ignore[no-untyped-def]
    org = str(uuid4())
    with _client(make_client) as c:
        viewer = _key(c, org, "viewer")  # viewer has no incidents:export
        assert (
            c.get(
                f"/security-export/incidents/{uuid4()}?format=json", headers=_headers(viewer, org)
            ).status_code
            == 403
        )
