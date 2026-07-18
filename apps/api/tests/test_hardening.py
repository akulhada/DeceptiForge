# Purpose: verify the demo-hardening fixes: route gating and scan restriction.
# Responsibilities: prove /demo/* mounts only when DEMO_ENABLED is true and that local-path
#   scanning is refused outside development/demo. Dependencies: the make_client factory.
from __future__ import annotations

from app.config.constants import DEMO_ORGANIZATION_ID
from app.config.settings import Settings
from app.services.demo import _FIXTURE_PATH

_AUTH = {
    "X-DeceptiForge-API-Key": "local-development-key",
    "X-DeceptiForge-Org-Id": str(DEMO_ORGANIZATION_ID),
}


def test_secure_defaults_disable_demo_and_local_path_scanning(monkeypatch) -> None:
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("DEMO_ENABLED", raising=False)
    settings = Settings(
        _env_file=None,
        database_url="postgresql+psycopg://unused:unused@localhost/deceptiforge",
    )

    assert settings.demo_enabled is False
    assert settings.is_development is False
    assert settings.allows_local_path_scan is False


def test_demo_routes_absent_when_disabled(make_client) -> None:
    with make_client(demo_enabled=False, app_env="production") as client:
        assert client.get("/demo/state").status_code == 404
        assert client.post("/demo/seed").status_code == 404


def test_demo_routes_present_in_development(make_client) -> None:
    with make_client(demo_enabled=True, app_env="development") as client:
        assert client.get("/demo/state").status_code == 200


def test_demo_routes_blocked_in_production_even_if_enabled(make_client) -> None:
    with make_client(demo_enabled=True, app_env="production") as client:
        assert client.get("/demo/state").status_code == 404
        assert client.post("/demo/run").status_code == 404


_BINDINGS = f'{{"prodkey": "{DEMO_ORGANIZATION_ID}"}}'
_PROD_AUTH = {"X-DeceptiForge-API-Key": "prodkey", "X-DeceptiForge-Org-Id": str(DEMO_ORGANIZATION_ID)}


def test_local_scan_rejected_in_production(make_client) -> None:
    with make_client(
        demo_enabled=False, auth_enabled=True, app_env="production", api_key_bindings=_BINDINGS
    ) as client:
        response = client.post(
            "/repositories/scan", json={"path": str(_FIXTURE_PATH)}, headers=_PROD_AUTH
        )
        assert response.status_code == 403


def test_local_scan_allowed_in_development(make_client) -> None:
    with make_client(demo_enabled=False, app_env="development") as client:
        response = client.post("/repositories/scan", json={"path": str(_FIXTURE_PATH)})
        assert response.status_code == 200


def test_local_scan_remains_blocked_in_production_demo_mode(make_client) -> None:
    with make_client(
        demo_enabled=True, auth_enabled=True, app_env="production", api_key_bindings=_BINDINGS
    ) as client:
        response = client.post(
            "/repositories/scan", json={"path": str(_FIXTURE_PATH)}, headers=_PROD_AUTH
        )
        assert response.status_code == 403
