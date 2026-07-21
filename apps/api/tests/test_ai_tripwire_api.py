# Purpose: verify the AI tripwire HTTP surface (RAG/MCP connectors, deployment lifecycle, signed
#   minimized event ingestion).
# Responsibilities: feature-flag gating, connector CRUD (secrets never returned), scopes, separation
#   of duties, deploy-before-approval rejection, cross-org isolation, a full create -> approve ->
#   deploy -> execute happy path via the worker, minimized event ingestion with deterministic
#   classification, replay rejection, and monitoring-not-active rejection.
from __future__ import annotations

import time
from uuid import UUID, uuid4

import pytest

from app.config.settings import get_settings
from app.services.ai_tripwire.connectors import FakeMcpAdapter, FakeRagAdapter
from app.services.ai_tripwire.worker import AiTripwireWorker
from app.services.api_keys import ApiKeyService


@pytest.fixture
def fakes(monkeypatch):  # type: ignore[no-untyped-def]
    rag = FakeRagAdapter()
    rag.register_collection("deceptiforge_decoys")
    mcp = FakeMcpAdapter()
    monkeypatch.setattr("app.api.ai_tripwire.build_rag_adapter", lambda: rag)
    monkeypatch.setattr("app.api.ai_tripwire.build_mcp_adapter", lambda: mcp)
    return rag, mcp


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
        rag_connectors_enabled=True,
        mcp_connectors_enabled=True,
        ai_tripwire_deployment_enabled=True,
    )


def _rag_connector(c, key: str, org: str) -> str:  # type: ignore[no-untyped-def]
    resp = c.post(
        "/rag-connectors",
        json={
            "name": "store",
            "connector_type": "pgvector",
            "index_or_collection": "deceptiforge_decoys",
            "secret": "s3cr3t-token",
        },
        headers=_headers(key, org),
    )
    assert resp.status_code == 201
    assert "s3cr3t-token" not in resp.text  # secret never returned
    return resp.json()["id"]


def _drive_to_deployed(c, rag, owner, approver, org) -> str:  # type: ignore[no-untyped-def]
    cid = _rag_connector(c, owner, org)
    did = c.post(
        "/ai-tripwire-deployments",
        json={
            "surface_type": "rag_document",
            "connector_id": cid,
            "target_collection": "deceptiforge_decoys",
            "decoy_kind": "architecture_note",
        },
        headers=_headers(owner, org),
    ).json()["id"]
    c.post(f"/ai-tripwire-deployments/{did}/submit", headers=_headers(owner, org))
    approve = c.post(
        f"/ai-tripwire-deployments/{did}/approve", json={}, headers=_headers(approver, org)
    )
    assert approve.status_code == 200
    deploy = c.post(f"/ai-tripwire-deployments/{did}/deploy", headers=_headers(approver, org))
    assert deploy.status_code == 200
    session = c.app_session()
    AiTripwireWorker(session, rag, FakeMcpAdapter(), get_settings()).run_once()
    session.commit()
    session.close()
    return did


def test_flag_off_hides_routes(make_client) -> None:  # type: ignore[no-untyped-def]
    org = str(uuid4())
    with make_client(auth_enabled=True, app_env="development") as c:
        key = _key(c, org, "owner")
        assert c.get("/rag-connectors", headers=_headers(key, org)).status_code == 404
        assert c.get("/ai-tripwire-deployments", headers=_headers(key, org)).status_code == 404


def test_cross_org_connector_isolation(make_client, fakes) -> None:  # type: ignore[no-untyped-def]
    rag, _ = fakes
    org_a, org_b = str(uuid4()), str(uuid4())
    with _client(make_client) as c:
        owner_a = _key(c, org_a, "owner")
        owner_b = _key(c, org_b, "owner")
        cid = _rag_connector(c, owner_a, org_a)
        # Org B cannot create a tripwire against org A's connector.
        resp = c.post(
            "/ai-tripwire-deployments",
            json={
                "surface_type": "rag_document",
                "connector_id": cid,
                "target_collection": "deceptiforge_decoys",
                "decoy_kind": "architecture_note",
            },
            headers=_headers(owner_b, org_b),
        )
        assert resp.status_code == 404


def test_separation_of_duties_enforced(make_client, fakes) -> None:  # type: ignore[no-untyped-def]
    rag, _ = fakes
    org = str(uuid4())
    with _client(make_client) as c:
        owner = _key(c, org, "owner")
        cid = _rag_connector(c, owner, org)
        did = c.post(
            "/ai-tripwire-deployments",
            json={
                "surface_type": "rag_document",
                "connector_id": cid,
                "target_collection": "deceptiforge_decoys",
                "decoy_kind": "architecture_note",
            },
            headers=_headers(owner, org),
        ).json()["id"]
        c.post(f"/ai-tripwire-deployments/{did}/submit", headers=_headers(owner, org))
        # The requester cannot approve their own deployment.
        resp = c.post(
            f"/ai-tripwire-deployments/{did}/approve", json={}, headers=_headers(owner, org)
        )
        assert resp.status_code == 403


def test_cannot_deploy_before_approval(make_client, fakes) -> None:  # type: ignore[no-untyped-def]
    rag, _ = fakes
    org = str(uuid4())
    with _client(make_client) as c:
        owner = _key(c, org, "owner")
        cid = _rag_connector(c, owner, org)
        did = c.post(
            "/ai-tripwire-deployments",
            json={
                "surface_type": "rag_document",
                "connector_id": cid,
                "target_collection": "deceptiforge_decoys",
                "decoy_kind": "architecture_note",
            },
            headers=_headers(owner, org),
        ).json()["id"]
        resp = c.post(f"/ai-tripwire-deployments/{did}/deploy", headers=_headers(owner, org))
        assert resp.status_code == 409  # draft -> deploying is illegal


def test_unapproved_collection_rejected(make_client, fakes) -> None:  # type: ignore[no-untyped-def]
    rag, _ = fakes
    org = str(uuid4())
    with _client(make_client) as c:
        owner = _key(c, org, "owner")
        cid = _rag_connector(c, owner, org)
        resp = c.post(
            "/ai-tripwire-deployments",
            json={
                "surface_type": "rag_document",
                "connector_id": cid,
                "target_collection": "prod_kb",
                "decoy_kind": "architecture_note",
            },
            headers=_headers(owner, org),
        )
        assert resp.status_code == 400  # collection not in allowlist


def test_happy_path_deploys_and_activates(make_client, fakes) -> None:  # type: ignore[no-untyped-def]
    rag, _ = fakes
    org = str(uuid4())
    with _client(make_client) as c:
        owner = _key(c, org, "owner")
        approver = _key(c, org, "owner")
        did = _drive_to_deployed(c, rag, owner, approver, org)
        final = c.get(f"/ai-tripwire-deployments/{did}", headers=_headers(approver, org)).json()
        assert final["status"] == "deployed"
        assert final["monitoring_activated"] is True
        assert rag.asset_count("deceptiforge_decoys") == 1


def test_event_ingestion_minimized_and_classified(make_client, fakes) -> None:  # type: ignore[no-untyped-def]
    rag, _ = fakes
    org = str(uuid4())
    with _client(make_client) as c:
        owner = _key(c, org, "owner")
        approver = _key(c, org, "owner")
        did = _drive_to_deployed(c, rag, owner, approver, org)
        trace = c.get(f"/ai-tripwire-deployments/{did}", headers=_headers(approver, org)).json()[
            "trace_id"
        ]
        service = _key(c, org, "service")
        resp = c.post(
            "/ai-tripwire-events",
            json={
                "trace_id": trace,
                "event_type": "document_retrieved",
                "source_id": "agent-9",
                "confidence": 0.9,
                "metadata": {
                    "collection": "deceptiforge_decoys",
                    "prompt": "RAW USER PROMPT",  # forbidden -> stripped
                    "output": "RAW MODEL ANSWER",  # forbidden -> stripped
                },
            },
            headers={
                **_headers(service, org),
                "X-DeceptiForge-Nonce": uuid4().hex,
                "X-DeceptiForge-Timestamp": str(time.time()),
            },
        )
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["accepted"] is True
        assert payload["exposure_type"] == "rag_retrieval_exposure"
        assert payload["event_count"] == 1
        # The stored event carries no raw prompt/output content.
        events = c.get(
            f"/ai-tripwire-deployments/{did}/events", headers=_headers(owner, org)
        ).json()
        assert len(events) == 1
        meta = events[0]["minimized_metadata"]
        assert "RAW USER PROMPT" not in meta and "RAW MODEL ANSWER" not in meta
        assert "collection" in meta


def test_event_replay_rejected(make_client, fakes) -> None:  # type: ignore[no-untyped-def]
    rag, _ = fakes
    org = str(uuid4())
    with _client(make_client) as c:
        owner = _key(c, org, "owner")
        approver = _key(c, org, "owner")
        did = _drive_to_deployed(c, rag, owner, approver, org)
        trace = c.get(f"/ai-tripwire-deployments/{did}", headers=_headers(approver, org)).json()[
            "trace_id"
        ]
        service = _key(c, org, "service")
        nonce = uuid4().hex
        headers = {
            **_headers(service, org),
            "X-DeceptiForge-Nonce": nonce,
            "X-DeceptiForge-Timestamp": str(time.time()),
        }
        body = {
            "trace_id": trace,
            "event_type": "document_retrieved",
            "source_id": "agent-9",
        }
        assert c.post("/ai-tripwire-events", json=body, headers=headers).status_code == 200
        # Reusing the same nonce is a replay and must be rejected.
        assert c.post("/ai-tripwire-events", json=body, headers=headers).status_code == 409


def test_event_rejected_when_monitoring_inactive(make_client, fakes) -> None:  # type: ignore[no-untyped-def]
    rag, _ = fakes
    org = str(uuid4())
    with _client(make_client) as c:
        owner = _key(c, org, "owner")
        cid = _rag_connector(c, owner, org)
        did = c.post(
            "/ai-tripwire-deployments",
            json={
                "surface_type": "rag_document",
                "connector_id": cid,
                "target_collection": "deceptiforge_decoys",
                "decoy_kind": "architecture_note",
            },
            headers=_headers(owner, org),
        ).json()["id"]
        trace = c.get(f"/ai-tripwire-deployments/{did}", headers=_headers(owner, org)).json()[
            "trace_id"
        ]
        service = _key(c, org, "service")
        resp = c.post(
            "/ai-tripwire-events",
            json={"trace_id": trace, "event_type": "document_retrieved", "source_id": "a"},
            headers={
                **_headers(service, org),
                "X-DeceptiForge-Nonce": uuid4().hex,
                "X-DeceptiForge-Timestamp": str(time.time()),
            },
        )
        assert resp.status_code == 409  # not yet deployed/verified
