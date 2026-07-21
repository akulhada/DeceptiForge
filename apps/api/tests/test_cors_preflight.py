# Purpose: verify the CORS contract matches what a browser page actually needs — and nothing more.
# The dashboard sends GET/POST with content-type, API key and org id. Signed monitoring ingestion is
# server-side or extension-originated (MV3 host_permissions bypass page CORS), so signing headers
# must NOT be advertised to browser origins.
from __future__ import annotations

ORIGIN = "http://localhost:3000"
OTHER_ORIGIN = "https://evil.example.com"


def _client(make_client):  # type: ignore[no-untyped-def]
    return make_client(
        demo_enabled=False,
        auth_enabled=True,
        app_env="development",
        cors_origins=f'["{ORIGIN}"]',
    )


def _preflight(client, method: str, headers: str = "content-type", origin: str = ORIGIN):  # type: ignore[no-untyped-def]
    return client.options(
        "/incidents",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": method,
            "Access-Control-Request-Headers": headers,
        },
    )


# ---- allowed surface -----------------------------------------------------------------------------


def test_allowed_origin_may_preflight_every_method_the_dashboard_uses(make_client) -> None:  # type: ignore[no-untyped-def]
    """Regression: PUT and DELETE are real dashboard calls (policy update and policy removal).

    browserSensorApi PUTs /browser-ai-policy; agentSensorApi PUTs and DELETEs
    /agent-scope-policies/{id}. Dropping them from the allow-list breaks policy administration at
    preflight, which is exactly what a narrowing pass must not do.
    """
    with _client(make_client) as client:
        for method in ("GET", "POST", "PUT", "DELETE"):
            response = _preflight(client, method)
            assert response.status_code == 200, method
            assert response.headers["access-control-allow-origin"] == ORIGIN


def test_dashboard_authentication_headers_are_allowed(make_client) -> None:  # type: ignore[no-untyped-def]
    with _client(make_client) as client:
        response = _preflight(
            client, "GET", headers="content-type,x-deceptiforge-api-key,x-deceptiforge-org-id"
        )
        assert response.status_code == 200
        allowed = response.headers["access-control-allow-headers"].lower()
        for header in ("content-type", "x-deceptiforge-api-key", "x-deceptiforge-org-id"):
            assert header in allowed


# ---- refused surface -----------------------------------------------------------------------------


def test_disallowed_origin_is_not_echoed(make_client) -> None:  # type: ignore[no-untyped-def]
    with _client(make_client) as client:
        response = _preflight(client, "GET", origin=OTHER_ORIGIN)
        assert response.headers.get("access-control-allow-origin") not in (OTHER_ORIGIN, "*")


def test_methods_no_client_uses_are_not_advertised(make_client) -> None:  # type: ignore[no-untyped-def]
    """No route accepts PATCH and no client sends it, so it stays off the allow-list."""
    with _client(make_client) as client:
        for method in ("PATCH", "TRACE"):
            response = _preflight(client, method)
            allowed = response.headers.get("access-control-allow-methods", "")
            assert method not in allowed, f"{method} must not be advertised to browsers"


def test_signing_headers_are_not_offered_to_browser_origins(make_client) -> None:  # type: ignore[no-untyped-def]
    """Signed ingestion is server-side/extension only.

    The MV3 extension uses host_permissions and does not traverse page CORS, so advertising
    signature or nonce headers here would only grant a browser page a capability it must not have.
    """
    with _client(make_client) as client:
        response = _preflight(
            client,
            "POST",
            headers="x-deceptiforge-signature,x-deceptiforge-monitor-id,x-deceptiforge-nonce",
        )
        allowed = response.headers.get("access-control-allow-headers", "").lower()
        for header in (
            "x-deceptiforge-signature",
            "x-deceptiforge-monitor-id",
            "x-deceptiforge-nonce",
            "x-deceptiforge-timestamp",
        ):
            assert header not in allowed, f"{header} must not be advertised to browsers"


def test_credentials_are_not_allowed_by_default(make_client) -> None:  # type: ignore[no-untyped-def]
    """Credentials stay off unless enabled, so a cookie cannot ride a cross-origin call."""
    with _client(make_client) as client:
        response = _preflight(client, "GET")
        assert response.headers.get("access-control-allow-credentials") != "true"


def test_cors_is_off_when_no_origins_are_configured(make_client) -> None:  # type: ignore[no-untyped-def]
    """Fail closed: with no allow-list the middleware is not attached at all."""
    with make_client(
        demo_enabled=False, auth_enabled=True, app_env="development", cors_origins="[]"
    ) as client:
        response = _preflight(client, "GET")
        assert response.headers.get("access-control-allow-origin") is None


def test_wildcard_origin_is_rejected_at_startup() -> None:
    import pytest
    from fastapi import FastAPI

    from app.middleware.cors import configure_cors

    with pytest.raises(ValueError, match="wildcard"):
        configure_cors(FastAPI(), ["*"], allow_credentials=True)
