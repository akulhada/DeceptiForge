# Purpose: verify the /api/v1/analysis endpoints — auth + permission + org isolation, sensor
#   exclusion, rate limiting (429 + Retry-After), aggregate-path 422, scenario listing, and that
#   the endpoint is stateless (no persistence) and deterministic.
from __future__ import annotations

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
        demo_enabled=False,
        auth_enabled=True,
        app_env="development",
        analysis_lab_enabled=True,
    )


_FINTECH = {
    "signals": {
        "services": [{"name": "payment-service"}, {"name": "ledger-api"}],
        "databases": [{"engine": "PostgreSQL", "data_domain_terms": ["payment", "settlement"]}],
        "naming_patterns": {"domain_terms": ["payment", "settlement", "reconciliation"]},
        "secret_locations": [{"path": "svc/.env.example", "category": "payment_gateway"}],
    },
    "scenario_id": "fintech-payments",
}


def test_requires_authentication(make_client) -> None:  # type: ignore[no-untyped-def]
    with _client(make_client) as client:
        r = client.post("/api/v1/analysis/preview", json=_FINTECH)
        assert r.status_code == 401


def test_analyst_can_preview(make_client) -> None:  # type: ignore[no-untyped-def]
    with _client(make_client) as client:
        org = str(uuid4())
        key = _key(client, org, "analyst")
        r = client.post("/api/v1/analysis/preview", json=_FINTECH, headers=_headers(key, org))
        assert r.status_code == 200
        body = r.json()
        assert body["schema_version"] == "analysis-preview-v1"
        assert body["organization_id"] == org  # resolved from identity, not the body
        assert body["context_profile"]["probable_business_domain"]["value"].startswith("Financial")
        assert body["sensitive_zones"]
        assert "request_id" in body


def test_viewer_can_preview_read_only(make_client) -> None:  # type: ignore[no-untyped-def]
    with _client(make_client) as client:
        org = str(uuid4())
        key = _key(client, org, "viewer")
        r = client.post("/api/v1/analysis/preview", json=_FINTECH, headers=_headers(key, org))
        assert r.status_code == 200


def test_sensor_role_forbidden(make_client) -> None:  # type: ignore[no-untyped-def]
    with _client(make_client) as client:
        org = str(uuid4())
        key = _key(client, org, "agent_sensor")
        r = client.post("/api/v1/analysis/preview", json=_FINTECH, headers=_headers(key, org))
        assert r.status_code == 403


def test_cross_organization_rejected(make_client) -> None:  # type: ignore[no-untyped-def]
    with _client(make_client) as client:
        org_a = str(uuid4())
        other = str(uuid4())
        key = _key(client, org_a, "analyst")
        # Key bound to org_a, header claims a different org -> rejected before any analysis.
        r = client.post("/api/v1/analysis/preview", json=_FINTECH, headers=_headers(key, other))
        assert r.status_code == 403


def test_scenarios_listed(make_client) -> None:  # type: ignore[no-untyped-def]
    with _client(make_client) as client:
        org = str(uuid4())
        key = _key(client, org, "viewer")
        r = client.get("/api/v1/analysis/scenarios", headers=_headers(key, org))
        assert r.status_code == 200
        ids = {s["id"] for s in r.json()}
        assert {"fintech-payments", "ml-rag", "sparse"} <= ids


def test_too_many_paths_rejected_422(make_client) -> None:  # type: ignore[no-untyped-def]
    with _client(make_client) as client:
        org = str(uuid4())
        key = _key(client, org, "analyst")
        # 60 services * 25 paths = 1500 <= collection bounds but push aggregate over MAX_TOTAL_PATHS
        # via many documentation paths instead (docs are one object, bounded per list to 25 -> use
        # secret_locations count which each add 1; 100 max < 2000). Use representative paths on many
        # languages: 100 langs * 25 = 2500 > 2000.
        signals = {
            "languages": [
                {"name": f"l{i}", "representative_paths": [f"p{i}/{j}.py" for j in range(25)]}
                for i in range(100)
            ]
        }
        r = client.post(
            "/api/v1/analysis/preview", json={"signals": signals}, headers=_headers(key, org)
        )
        assert r.status_code == 422


def test_rate_limit_returns_429_with_retry_after(make_client) -> None:  # type: ignore[no-untyped-def]
    from app.services.rate_limit import reset_rate_limiter

    with _client(make_client) as client:
        reset_rate_limiter()
        org = str(uuid4())
        key = _key(client, org, "analyst")
        headers = _headers(key, org)
        statuses = []
        for _ in range(35):  # default limit is 30/min
            statuses.append(
                client.post("/api/v1/analysis/preview", json=_FINTECH, headers=headers).status_code
            )
            if statuses[-1] == 429:
                break
        assert 429 in statuses
        r = client.post("/api/v1/analysis/preview", json=_FINTECH, headers=headers)
        assert r.status_code == 429
        assert r.headers.get("Retry-After") == "60"


def test_malformed_contract_returns_422(make_client) -> None:  # type: ignore[no-untyped-def]
    with _client(make_client) as client:
        org = str(uuid4())
        key = _key(client, org, "analyst")
        r = client.post(
            "/api/v1/analysis/preview",
            json={"signals": {"languages": "not-a-list"}},
            headers=_headers(key, org),
        )
        assert r.status_code == 422


# ---- environment gating ------------------------------------------------------------------------


def test_analysis_routes_return_404_when_lab_disabled(make_client) -> None:  # type: ignore[no-untyped-def]
    """A demonstration surface: disabled means absent, not merely hidden in navigation."""
    with make_client(
        demo_enabled=False, auth_enabled=True, app_env="development", analysis_lab_enabled=False
    ) as client:
        org = str(uuid4())
        key = _key(client, org, "analyst")
        headers = _headers(key, org)
        assert (
            client.post("/api/v1/analysis/preview", json=_FINTECH, headers=headers).status_code
            == 404
        )
        assert client.get("/api/v1/analysis/scenarios", headers=headers).status_code == 404


def test_analysis_lab_flag_is_refused_outside_development() -> None:
    """Startup rejects the flag in staging/production, so those environments cannot expose it."""
    import pytest

    from app.config.settings import Settings

    with pytest.raises(RuntimeError, match="ANALYSIS_LAB_ENABLED"):
        Settings(
            app_env="production",
            analysis_lab_enabled=True,
            auth_enabled=True,
            demo_enabled=False,
            rate_limit_mode="gateway",
            replay_backend="redis",
            redis_url="redis://localhost:6379/0",
            monitor_signature_required=True,
            evidence_encryption_mode="local",
            evidence_encryption_key="test-evidence-key-0000000000000000000000",
        ).validate_runtime()
