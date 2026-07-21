# Purpose: verify the decoy-deployment HTTP surface.
# Responsibilities: feature flag gating, permission scopes, separation-of-duties, state-transition
#   enforcement, cross-org isolation, and a full create -> approve -> deploy -> verify happy path
#   driven through the worker + in-memory GitHub adapter (no monitoring before a verified merge).
from __future__ import annotations

from uuid import UUID, uuid4

from _deploy_factories import make_asset, make_plan, make_report

from app.config.settings import get_settings
from app.repositories.artifacts import ArtifactRepository
from app.services.api_keys import ApiKeyService
from app.services.deployment.github_port import FakeDeploymentClient
from app.services.deployment.service import resolve_repo
from app.services.deployment.worker import DeploymentWorker

_BASE = "base0000"


def _key(client, org: str, role: str) -> str:  # type: ignore[no-untyped-def]
    session = client.app_session()
    _, plaintext = ApiKeyService(session).create(UUID(org), role, role)
    session.commit()
    session.close()
    return plaintext


def _seed_plan(client, org: str, path: str = "docs/decoys/runbook.md") -> tuple[str, str]:
    session = client.app_session()
    art = ArtifactRepository(session, get_settings().max_artifact_bytes)
    asset = make_asset(path)
    plan_id = art.add_decoy_plan(UUID(org), uuid4(), make_plan(asset))
    art.add_validation_report(UUID(org), plan_id, make_report(asset.decoy_id))
    session.commit()
    session.close()
    return str(plan_id), str(uuid4())


def _headers(key: str, org: str) -> dict[str, str]:
    return {"X-DeceptiForge-API-Key": key, "X-DeceptiForge-Org-Id": org}


def _client(make_client):  # type: ignore[no-untyped-def]
    return make_client(
        demo_enabled=False, auth_enabled=True, app_env="development", decoy_deployment_enabled=True
    )


def _run_worker(client, fake: FakeDeploymentClient) -> None:  # type: ignore[no-untyped-def]
    session = client.app_session()
    DeploymentWorker(session, fake, get_settings()).run_once()
    session.commit()
    session.close()


def _create(client, key: str, org: str, plan_id: str, repo_id: str):  # type: ignore[no-untyped-def]
    return client.post(
        "/decoy-deployments",
        json={"repository_id": repo_id, "decoy_plan_id": plan_id, "base_commit_sha": _BASE},
        headers=_headers(key, org),
    )


def test_feature_flag_off_hides_routes(make_client) -> None:  # type: ignore[no-untyped-def]
    org = str(uuid4())
    with make_client(auth_enabled=True, app_env="development", decoy_deployment_enabled=False) as c:
        key = _key(c, org, "owner")
        assert c.get("/decoy-deployments", headers=_headers(key, org)).status_code == 404


def test_viewer_cannot_create_analyst_can(make_client) -> None:  # type: ignore[no-untyped-def]
    org = str(uuid4())
    with _client(make_client) as c:
        plan_id, repo_id = _seed_plan(c, org)
        viewer = _key(c, org, "viewer")
        analyst = _key(c, org, "analyst")
        assert _create(c, viewer, org, plan_id, repo_id).status_code == 403
        created = _create(c, analyst, org, plan_id, repo_id)
        assert created.status_code == 201
        assert created.json()["status"] == "draft"


def test_separation_of_duties_blocks_self_approval(make_client) -> None:  # type: ignore[no-untyped-def]
    org = str(uuid4())
    with _client(make_client) as c:
        plan_id, repo_id = _seed_plan(c, org)
        owner = _key(c, org, "owner")  # owner can both create and approve
        did = _create(c, owner, org, plan_id, repo_id).json()["id"]
        c.post(f"/decoy-deployments/{did}/submit", headers=_headers(owner, org))
        # Same actor tries to approve their own submission -> rejected by separation of duties.
        resp = c.post(f"/decoy-deployments/{did}/approve", json={}, headers=_headers(owner, org))
        assert resp.status_code == 403


def test_cannot_deploy_before_approval(make_client) -> None:  # type: ignore[no-untyped-def]
    org = str(uuid4())
    with _client(make_client) as c:
        plan_id, repo_id = _seed_plan(c, org)
        owner = _key(c, org, "owner")
        did = _create(c, owner, org, plan_id, repo_id).json()["id"]
        # draft -> deploying is not a legal transition.
        deploy = c.post(f"/decoy-deployments/{did}/deploy", headers=_headers(owner, org))
        assert deploy.status_code == 409


def test_cross_org_access_returns_404(make_client) -> None:  # type: ignore[no-untyped-def]
    org, other = str(uuid4()), str(uuid4())
    with _client(make_client) as c:
        plan_id, repo_id = _seed_plan(c, org)
        owner = _key(c, org, "owner")
        other_owner = _key(c, other, "owner")
        did = _create(c, owner, org, plan_id, repo_id).json()["id"]
        seen = c.get(f"/decoy-deployments/{did}", headers=_headers(other_owner, other))
        assert seen.status_code == 404


def test_happy_path_deploys_and_activates_after_merge(make_client) -> None:  # type: ignore[no-untyped-def]
    org = str(uuid4())
    with _client(make_client) as c:
        plan_id, repo_id = _seed_plan(c, org)
        requester = _key(c, org, "analyst")  # creates + submits
        approver = _key(c, org, "owner")  # approves + deploys
        fake = FakeDeploymentClient()
        fake.register_repo(resolve_repo(UUID(org), UUID(repo_id), "main"), base_sha=_BASE)

        did = _create(c, requester, org, plan_id, repo_id).json()["id"]
        prev = c.get(f"/decoy-deployments/{did}/preview", headers=_headers(requester, org))
        assert prev.status_code == 200
        c.post(f"/decoy-deployments/{did}/submit", headers=_headers(requester, org))
        assert (
            c.post(
                f"/decoy-deployments/{did}/approve", json={}, headers=_headers(approver, org)
            ).json()["status"]
            == "approved"
        )
        c.post(f"/decoy-deployments/{did}/deploy", headers=_headers(approver, org))

        _run_worker(c, fake)  # execute: opens the PR
        after_execute = c.get(f"/decoy-deployments/{did}", headers=_headers(approver, org)).json()
        assert after_execute["status"] == "deploying"
        assert after_execute["pull_request_number"] is not None
        assert after_execute["monitoring_activated"] is False  # not before merge

        repo = resolve_repo(UUID(org), UUID(repo_id), "main")
        fake.merge_pull_request(repo, after_execute["pull_request_number"])

        # Enqueue + run verify (a poller/webhook does this in production).
        session = c.app_session()
        from app.repositories.deployments import DeploymentRepository, new_correlation_id

        DeploymentRepository(session).enqueue_job(
            organization_id=UUID(org),
            deployment_id=UUID(did),
            job_type="verify",
            correlation_id=new_correlation_id(),
        )
        session.commit()
        session.close()
        _run_worker(c, fake)

        final = c.get(f"/decoy-deployments/{did}", headers=_headers(approver, org)).json()
        assert final["status"] == "deployed"
        assert final["monitoring_activated"] is True

        audit = c.get(f"/decoy-deployments/{did}/audit", headers=_headers(approver, org)).json()
        events = {e["event_type"] for e in audit}
        assert {"deployment_created", "approved", "pr_created", "monitoring_activated"} <= events
