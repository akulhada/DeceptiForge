# Purpose: verify the database-honey HTTP surface.
# Responsibilities: feature-flag gating, connector CRUD (secrets never returned) + test/sync via a
#   monkeypatched fake client, permission scopes, separation of duties, deploy-before-approval
#   rejection, cross-org isolation, and a full create -> approve -> deploy -> execute happy path.
from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.config.settings import get_settings
from app.models.domain.database_honey import ColumnInfo, TableInfo
from app.services.api_keys import ApiKeyService
from app.services.database.connector_port import FakeDatabaseClient
from app.services.database.worker import DatabaseHoneyWorker


def _customers() -> TableInfo:
    def col(name, dtype="varchar", **kw):  # type: ignore[no-untyped-def]
        return ColumnInfo(name=name, data_type=dtype, is_nullable=kw.pop("nullable", False), **kw)

    return TableInfo(
        schema_name="public",
        table_name="customers",
        columns=(
            col("id", "uuid", is_primary_key=True),
            col("email", "varchar", max_length=255),
            col("full_name", "varchar", max_length=120),
            col("status", "varchar", enum_values=("active", "inactive")),
        ),
        primary_key=("id",),
    )


@pytest.fixture
def fake_client(monkeypatch) -> FakeDatabaseClient:  # type: ignore[no-untyped-def]
    client = FakeDatabaseClient()
    client.register_table(_customers())
    monkeypatch.setattr("app.api.database_honey.build_connector_client", lambda: client)
    return client


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
        database_connectors_enabled=True,
        database_honey_deployment_enabled=True,
    )


def _make_connector(c, key: str, org: str) -> str:  # type: ignore[no-untyped-def]
    resp = c.post(
        "/database-connectors",
        json={
            "name": "warehouse",
            "host_reference": "db.internal",
            "database_name": "app",
            "user": "deceptiforge_writer",
            "password": "s3cr3t",
            "ssl_mode": "require",
        },
        headers=_headers(key, org),
    )
    assert resp.status_code == 201
    assert "password" not in resp.text and "s3cr3t" not in resp.text  # secret never returned
    return resp.json()["id"]


def test_flag_off_hides_routes(make_client) -> None:  # type: ignore[no-untyped-def]
    org = str(uuid4())
    with make_client(auth_enabled=True, app_env="development") as c:
        key = _key(c, org, "owner")
        assert c.get("/database-connectors", headers=_headers(key, org)).status_code == 404


def test_connector_crud_and_sync(make_client, fake_client) -> None:  # type: ignore[no-untyped-def]
    org = str(uuid4())
    with _client(make_client) as c:
        owner = _key(c, org, "owner")
        cid = _make_connector(c, owner, org)
        tested = c.post(f"/database-connectors/{cid}/test", headers=_headers(owner, org))
        assert tested.status_code == 200
        synced = c.post(f"/database-connectors/{cid}/sync-schema", headers=_headers(owner, org))
        assert synced.status_code == 200 and synced.json()["tables"] == 1


def test_viewer_cannot_manage_connector(make_client, fake_client) -> None:  # type: ignore[no-untyped-def]
    org = str(uuid4())
    with _client(make_client) as c:
        viewer = _key(c, org, "viewer")
        resp = c.post(
            "/database-connectors",
            json={
                "name": "x",
                "host_reference": "h",
                "database_name": "d",
                "user": "u",
                "password": "p",
            },
            headers=_headers(viewer, org),
        )
        assert resp.status_code == 403


def test_happy_path_deploys_and_activates(make_client, fake_client) -> None:  # type: ignore[no-untyped-def]
    org = str(uuid4())
    with _client(make_client) as c:
        requester = _key(c, org, "analyst")
        approver = _key(c, org, "owner")
        cid = _make_connector(c, approver, org)
        c.post(f"/database-connectors/{cid}/sync-schema", headers=_headers(approver, org))

        created = c.post(
            "/database-honey-deployments",
            json={"connector_id": cid, "target_schema": "public", "target_table": "customers"},
            headers=_headers(requester, org),
        )
        assert created.status_code == 201
        did = created.json()["id"]
        assert (
            c.get(
                f"/database-honey-deployments/{did}/preview", headers=_headers(requester, org)
            ).status_code
            == 200
        )

        c.post(f"/database-honey-deployments/{did}/submit", headers=_headers(requester, org))
        # Separation of duties: requester (analyst) lacks approve scope anyway.
        assert (
            c.post(
                f"/database-honey-deployments/{did}/approve",
                json={},
                headers=_headers(requester, org),
            ).status_code
            == 403
        )
        approved = c.post(
            f"/database-honey-deployments/{did}/approve", json={}, headers=_headers(approver, org)
        )
        assert approved.json()["status"] == "approved"
        c.post(f"/database-honey-deployments/{did}/deploy", headers=_headers(approver, org))

        # Drain the worker with the same fake client.
        session = c.app_session()
        DatabaseHoneyWorker(session, fake_client, get_settings()).run_once()
        session.commit()
        session.close()

        final = c.get(f"/database-honey-deployments/{did}", headers=_headers(approver, org)).json()
        assert final["status"] == "deployed"
        assert final["monitoring_activated"] is True
        assert fake_client.row_count("public", "customers") == 1


def test_cannot_deploy_before_approval(make_client, fake_client) -> None:  # type: ignore[no-untyped-def]
    org = str(uuid4())
    with _client(make_client) as c:
        owner = _key(c, org, "owner")
        cid = _make_connector(c, owner, org)
        c.post(f"/database-connectors/{cid}/sync-schema", headers=_headers(owner, org))
        did = c.post(
            "/database-honey-deployments",
            json={"connector_id": cid, "target_schema": "public", "target_table": "customers"},
            headers=_headers(owner, org),
        ).json()["id"]
        deploy = c.post(f"/database-honey-deployments/{did}/deploy", headers=_headers(owner, org))
        assert deploy.status_code == 409  # draft -> deploying is illegal


def test_cross_org_deployment_isolation(make_client, fake_client) -> None:  # type: ignore[no-untyped-def]
    org, other = str(uuid4()), str(uuid4())
    with _client(make_client) as c:
        owner = _key(c, org, "owner")
        other_owner = _key(c, other, "owner")
        cid = _make_connector(c, owner, org)
        c.post(f"/database-connectors/{cid}/sync-schema", headers=_headers(owner, org))
        did = c.post(
            "/database-honey-deployments",
            json={"connector_id": cid, "target_schema": "public", "target_table": "customers"},
            headers=_headers(owner, org),
        ).json()["id"]
        seen = c.get(f"/database-honey-deployments/{did}", headers=_headers(other_owner, other))
        assert seen.status_code == 404
