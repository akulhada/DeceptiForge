# Purpose: verify the production-readiness master stabilization fixes.
# Responsibilities: hashed/scoped/revocable API keys and RBAC, monitor ingest permission + replay,
#   episode-scoped incident identity and lifecycle, rate-limit config guard, tenant read auth, and
#   admin key endpoints. Dependencies: client/make_client, direct services, and a seeded session.
from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config.settings import Settings
from app.database.base import Base
from app.models import records as _records  # noqa: F401
from app.models.domain.operations import (
    AlertEvidence,
    IncidentLifecycle,
    MonitorType,
    NormalizedAlert,
    Severity,
)
from app.repositories.artifacts import ArtifactRepository
from app.services.api_keys import ApiKeyService, AuthError, hash_key
from app.services.incident_reconstruction import IncidentReconstructionEngine

_DB_URL = "postgresql+psycopg://unused:unused@localhost/deceptiforge"


def _session():  # type: ignore[no-untyped-def]
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


# ---- P0: hashed, scoped, revocable, expirable API keys -------------------------------------------


def test_api_key_is_hashed_and_authenticates_by_prefix() -> None:
    session = _session()
    service = ApiKeyService(session)
    org = uuid4()
    record, plaintext = service.create(org, "ci", "analyst")

    assert record.key_hash != plaintext and record.key_hash == hash_key(plaintext)
    context = service.authenticate(plaintext)
    assert context.organization_id == org
    assert "incidents:read" in context.scopes and "repositories:write" not in context.scopes


def test_revoked_and_expired_keys_are_rejected() -> None:
    session = _session()
    service = ApiKeyService(session)
    org = uuid4()
    revoked, revoked_plain = service.create(org, "k", "viewer")
    service.revoke(org, revoked.id)
    expired, expired_plain = service.create(
        org, "k", "viewer", expires_at=datetime.now(UTC) - timedelta(hours=1)
    )

    with pytest.raises(AuthError):
        service.authenticate(revoked_plain)
    with pytest.raises(AuthError):
        service.authenticate(expired_plain)


def _seed_key(client, org: str, role: str) -> str:  # type: ignore[no-untyped-def]
    session = client.app_session()
    _, plaintext = ApiKeyService(session).create(UUID(org), "t", role)
    session.commit()
    session.close()
    return plaintext


def test_viewer_cannot_write_and_read_only_key_cannot_ingest(make_client) -> None:
    org = str(uuid4())
    with make_client(demo_enabled=False, auth_enabled=True, app_env="production") as client:
        viewer = _seed_key(client, org, "viewer")
        headers = {"X-DeceptiForge-API-Key": viewer, "X-DeceptiForge-Org-Id": org}
        # viewer can read
        assert client.get("/incidents", headers=headers).status_code == 200
        # viewer cannot write / ingest
        assert (
            client.post(
                "/placements/plan", json={"repository_id": str(uuid4())}, headers=headers
            ).status_code
            == 403
        )
        assert (
            client.post(
                "/monitoring/events",
                json={
                    "decoy_plan_id": str(uuid4()),
                    "surface": "repository",
                    "location": "x",
                    "value": "y",
                },
                headers=headers,
            ).status_code
            == 403
        )


# ---- P1: monitor ingest replay protection --------------------------------------------------------


def test_monitor_replay_and_timestamp_are_enforced(make_client) -> None:
    org = str(uuid4())
    with make_client(demo_enabled=False, auth_enabled=True, app_env="production") as client:
        service_key = _seed_key(client, org, "service")
        base = {"X-DeceptiForge-API-Key": service_key, "X-DeceptiForge-Org-Id": org}
        body = {
            "decoy_plan_id": str(uuid4()),
            "surface": "repository",
            "location": "x",
            "value": "y",
        }
        now = str(int(time.time()))

        # Missing nonce/timestamp -> 400
        assert client.post("/monitoring/events", json=body, headers=base).status_code == 400
        # Old timestamp -> 400
        old = {**base, "X-DeceptiForge-Nonce": "n1", "X-DeceptiForge-Timestamp": "1"}
        assert client.post("/monitoring/events", json=body, headers=old).status_code == 400
        # Valid nonce -> reaches pipeline (decoy plan missing for this org -> 409, not a replay
        # error)
        fresh = {**base, "X-DeceptiForge-Nonce": "n2", "X-DeceptiForge-Timestamp": now}
        first = client.post("/monitoring/events", json=body, headers=fresh)
        assert first.status_code in {200, 409}
        # Replayed nonce -> 409
        assert client.post("/monitoring/events", json=body, headers=fresh).status_code == 409


# ---- P1: incident identity + lifecycle -----------------------------------------------------------


def _alert(trace: str, monitor: MonitorType, at: datetime) -> NormalizedAlert:
    return NormalizedAlert(
        alert_id=uuid4(),
        trace_identifier=trace,
        decoy_id=uuid4(),
        severity=Severity.HIGH,
        title="t",
        summary="observed",
        source_monitor=monitor,
        confidence=0.9,
        first_seen=at,
        last_seen=at,
        event_count=1,
        deduplication_key=f"{trace}:id:{monitor.value}:path:repository:content_access",
        affected_placement_id=uuid4(),
        affected_decoy_type="secret",
        evidence=(AlertEvidence(excerpt=trace, digest="a" * 64, location="src/x.py"),),
        raw_event_ids=(uuid4(),),
        recommended_actions=("review",),
        correlation_id=uuid4(),
    )


def test_same_trace_in_separate_episodes_creates_new_incident() -> None:
    org = uuid4()
    engine = IncidentReconstructionEngine()
    now = datetime.now(UTC)
    within = engine.reconstruct(
        (
            _alert("DFG-T", MonitorType.REPOSITORY, now),
            _alert("DFG-T", MonitorType.REPOSITORY, now + timedelta(minutes=5)),
        ),
        organization_id=org,
    )
    later = engine.reconstruct(
        (_alert("DFG-T", MonitorType.REPOSITORY, now + timedelta(hours=3)),),
        organization_id=org,
    )
    assert len(within) == 1
    assert within[0].incident_id != later[0].incident_id  # separate episode -> new incident


def test_stale_incident_lifecycle_is_org_scoped() -> None:
    repo = ArtifactRepository(_session())
    org_a, org_b = uuid4(), uuid4()
    engine = IncidentReconstructionEngine()
    old = datetime.now(UTC) - timedelta(days=3)
    repo.add_alert(org_a, _alert("DFG-A", MonitorType.REPOSITORY, old))
    repo.add_alert(org_b, _alert("DFG-B", MonitorType.REPOSITORY, old))
    repo.upsert_incidents_for_organization(
        org_a, engine.reconstruct(repo.alerts_for_organization(org_a), organization_id=org_a)
    )
    repo.upsert_incidents_for_organization(
        org_b, engine.reconstruct(repo.alerts_for_organization(org_b), organization_id=org_b)
    )

    retired = repo.retire_stale_incidents(org_a, datetime.now(UTC), 86_400)
    assert retired == 1
    assert repo.incidents_for_organization(org_a)[0].lifecycle is IncidentLifecycle.STALE
    assert repo.incidents_for_organization(org_b)[0].lifecycle is IncidentLifecycle.OPEN


# ---- rate-limit config guard + tenant auth + admin -----------------------------------------------


def test_production_app_rate_limiting_requires_redis() -> None:
    settings = Settings(
        _env_file=None,
        database_url=_DB_URL,
        app_env="production",
        rate_limit_mode="app",
    )  # type: ignore[call-arg]
    with pytest.raises(RuntimeError):
        settings.validate_runtime()


def test_tenant_endpoints_require_authentication(make_client) -> None:
    with make_client(demo_enabled=False, auth_enabled=True, app_env="production") as client:
        assert client.get("/whoami").status_code == 401
        assert client.get("/repositories").status_code == 401


def test_admin_can_create_list_and_revoke_keys(client) -> None:
    created = client.post("/admin/api-keys", json={"name": "ci", "role": "analyst"})
    assert created.status_code == 200
    plaintext = created.json()["api_key"]
    assert plaintext.startswith("dfk_")
    key_id = created.json()["key"]["id"]

    listing = client.get("/admin/api-keys").json()
    assert any(item["id"] == key_id for item in listing)
    assert all("api_key" not in item for item in listing)  # plaintext never returned again

    assert client.delete(f"/admin/api-keys/{key_id}").status_code == 204
