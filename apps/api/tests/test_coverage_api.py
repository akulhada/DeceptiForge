# Purpose: verify the coverage HTTP surface + scheduled job — flag gating, honest empty state,
#   recalculate builds a snapshot from real controls, idempotent snapshots, immutability,
#   recommendation accept-is-draft-only, cross-org isolation, methodology, and policy.
from __future__ import annotations

from uuid import UUID, uuid4

from app.jobs.coverage import run as run_coverage_job
from app.models.records import DecoyDeploymentRecord, RepositoryRecord
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
        coverage_engine_enabled=True,
    )


def _seed_repo_decoy(client, org: str, *, status="deployed", monitoring=True) -> None:  # type: ignore[no-untyped-def]
    from datetime import UTC, datetime

    session = client.app_session()
    repo = RepositoryRecord(
        organization_id=UUID(org),
        name="billing-app",
        root_path="/r",
        profile="{}",
    )
    session.add(repo)
    session.flush()
    session.add(
        DecoyDeploymentRecord(
            organization_id=UUID(org),
            repository_id=repo.id,
            decoy_plan_id=uuid4(),
            validation_report_decision="accepted",
            status=status,
            target_branch="main",
            source_branch="df",
            base_commit_sha="a" * 40,
            monitoring_activated_at=datetime.now(UTC) if monitoring else None,
            deployed_at=datetime.now(UTC),
        )
    )
    session.commit()
    session.close()


def test_flag_off_hides_routes(make_client) -> None:  # type: ignore[no-untyped-def]
    org = str(uuid4())
    with make_client(auth_enabled=True, app_env="development") as c:
        key = _key(c, org, "owner")
        assert c.get("/coverage", headers=_headers(key, org)).status_code == 404


def test_empty_state_is_honest(make_client) -> None:  # type: ignore[no-untyped-def]
    org = str(uuid4())
    with _client(make_client) as c:
        key = _key(c, org, "viewer")
        body = c.get("/coverage", headers=_headers(key, org)).json()
        assert body["status"] == "no_snapshot"  # never a fabricated 100%


def test_recalculate_builds_snapshot_and_is_idempotent(make_client) -> None:  # type: ignore[no-untyped-def]
    org = str(uuid4())
    with _client(make_client) as c:
        _seed_repo_decoy(c, org)
        admin = _key(c, org, "admin")
        first = c.post("/coverage/recalculate", headers=_headers(admin, org))
        assert first.status_code == 200
        assert first.json()["active_decoys"] == 1
        assert 0.0 < first.json()["overall_score"] <= 1.0
        hash1 = first.json()["source_state_hash"]
        # Same state -> idempotent: no new snapshot, same hash.
        c.post("/coverage/recalculate", headers=_headers(admin, org))
        snapshots = c.get("/coverage/snapshots", headers=_headers(admin, org)).json()
        assert len(snapshots) == 1
        assert snapshots[0]["source_state_hash"] == hash1


def test_snapshot_is_immutable_history(make_client) -> None:  # type: ignore[no-untyped-def]
    org = str(uuid4())
    with _client(make_client) as c:
        _seed_repo_decoy(c, org)
        admin = _key(c, org, "admin")
        c.post("/coverage/recalculate", headers=_headers(admin, org))
        s1 = c.get("/coverage/snapshots", headers=_headers(admin, org)).json()[0]
        # Add another decoy -> state changes -> a NEW snapshot, old one unchanged.
        _seed_repo_decoy(c, org)
        c.post("/coverage/recalculate", headers=_headers(admin, org))
        snapshots = c.get("/coverage/snapshots", headers=_headers(admin, org)).json()
        assert len(snapshots) == 2
        old = next(s for s in snapshots if s["id"] == s1["id"])
        assert old["source_state_hash"] == s1["source_state_hash"]
        assert old["overall_score"] == s1["overall_score"]


def test_recommendation_accept_is_draft_only(make_client) -> None:  # type: ignore[no-untyped-def]
    org = str(uuid4())
    with _client(make_client) as c:
        # A repo with NO decoy -> a gap + recommendation.
        session = c.app_session()
        session.add(
            RepositoryRecord(
                organization_id=UUID(org),
                name="auth-service",
                root_path="/r",
                profile="{}",
            )
        )
        session.commit()
        session.close()
        admin = _key(c, org, "admin")
        c.post("/coverage/recalculate", headers=_headers(admin, org))
        recs = c.get("/coverage/recommendations", headers=_headers(admin, org)).json()
        assert len(recs) >= 1
        resp = c.post(
            f"/coverage/recommendations/{recs[0]['id']}/accept", headers=_headers(admin, org)
        )
        assert resp.status_code == 200
        assert resp.json()["auto_deployed"] is False  # never auto-deploys


def test_cross_org_isolation(make_client) -> None:  # type: ignore[no-untyped-def]
    org_a, org_b = str(uuid4()), str(uuid4())
    with _client(make_client) as c:
        _seed_repo_decoy(c, org_a)
        admin_a = _key(c, org_a, "admin")
        admin_b = _key(c, org_b, "admin")
        c.post("/coverage/recalculate", headers=_headers(admin_a, org_a))
        # Org B sees no snapshots from org A.
        assert c.get("/coverage/snapshots", headers=_headers(admin_b, org_b)).json() == []
        body_b = c.get("/coverage", headers=_headers(admin_b, org_b)).json()
        assert body_b["status"] == "no_snapshot"


def test_methodology_and_policy(make_client) -> None:  # type: ignore[no-untyped-def]
    org = str(uuid4())
    with _client(make_client) as c:
        admin = _key(c, org, "admin")
        meth = c.get("/coverage/methodology", headers=_headers(admin, org)).json()
        assert meth["methodology_version"] == "coverage-v1"
        assert abs(sum(meth["dimension_weights"].values()) - 1.0) < 1e-6
        v1 = c.put(
            "/coverage/policy",
            json={"recommendation_risk_tolerance": 0.3},
            headers=_headers(admin, org),
        ).json()["policy_version"]
        v2 = c.put(
            "/coverage/policy",
            json={"recommendation_risk_tolerance": 0.4},
            headers=_headers(admin, org),
        ).json()["policy_version"]
        assert v2 > v1


def test_scheduled_job_idempotent(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from datetime import UTC, datetime

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from app.config.settings import Settings
    from app.database.base import Base

    eng = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(eng)
    factory = sessionmaker(bind=eng, expire_on_commit=False)
    seed = factory()
    org = uuid4()
    repo = RepositoryRecord(organization_id=org, name="app", root_path="/r", profile="{}")
    seed.add(repo)
    seed.flush()
    seed.add(
        DecoyDeploymentRecord(
            organization_id=org,
            repository_id=repo.id,
            decoy_plan_id=uuid4(),
            validation_report_decision="accepted",
            status="deployed",
            target_branch="main",
            source_branch="df",
            base_commit_sha="a" * 40,
            monitoring_activated_at=datetime.now(UTC),
            deployed_at=datetime.now(UTC),
        )
    )
    seed.commit()
    seed.close()

    monkeypatch.setattr("app.jobs._runtime.get_sessionmaker", lambda: factory)
    settings = Settings(
        database_url="postgresql+psycopg://u:p@localhost/db",  # type: ignore[arg-type]
        app_env="development",
        coverage_engine_enabled=True,
    )
    r1 = run_coverage_job(settings)
    r2 = run_coverage_job(settings)
    assert r1["snapshots_created"] >= 1
    assert r2["snapshots_created"] == 0  # unchanged state -> no new snapshot
