# Purpose: prove the decoy-deployment lifecycle against the in-memory GitHub adapter.
# Responsibilities: monitoring never activates before a verified merge; activates after; closed-
#   unmerged PRs cancel without activation; base drift blocks deployment; duplicate jobs do not
#   create duplicate PRs; retirement/rollback remove only owned files and disable monitoring; cross-
#   org access is blocked; verification mismatch fails safely.
from __future__ import annotations

from uuid import uuid4

import pytest
from _deploy_factories import make_asset, make_plan, make_report
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config.settings import Settings
from app.database.base import Base
from app.models import records as _records  # noqa: F401
from app.models.domain.deployment import DeploymentStatus
from app.repositories.artifacts import ArtifactRepository
from app.repositories.deployments import DeploymentNotFoundError, DeploymentRepository
from app.services.deployment.github_port import FakeDeploymentClient
from app.services.deployment.policy import PathPolicy
from app.services.deployment.preview import build_preview
from app.services.deployment.service import DeploymentService, resolve_repo
from app.services.encryption import NoopEncryptionProvider

_BASE = "base0000"


def _settings() -> Settings:
    return Settings(
        database_url="postgresql+psycopg://u:p@localhost/db",  # type: ignore[arg-type]
        app_env="development",
    )


def _engine() -> Engine:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    return engine


class _Ctx:
    def __init__(self, session: Session, path: str = "docs/decoys/runbook.md") -> None:
        self.settings = _settings()
        self.session = session
        self.art = ArtifactRepository(session, encryption=NoopEncryptionProvider())
        self.dep = DeploymentRepository(session)
        self.client = FakeDeploymentClient()
        self.org = uuid4()
        self.repo_id = uuid4()
        asset = make_asset(path)
        plan = make_plan(asset)
        self.report = make_report(asset.decoy_id)
        self.plan_id = self.art.add_decoy_plan(self.org, self.repo_id, plan)
        self.art.add_validation_report(self.org, self.plan_id, self.report)
        self.record = self.dep.create(
            organization_id=self.org, repository_id=self.repo_id, decoy_plan_id=self.plan_id,
            validation_decision="accept", requested_by_actor_id=uuid4(),
            target_branch="deceptiforge/decoy-x", source_branch="main",
            base_commit_sha=_BASE, expires_at=None,
        )
        preview, contents = build_preview(
            deployment_id=self.record.id, repository_id=self.repo_id, base_branch="main",
            base_commit_sha=_BASE, target_branch=f"deceptiforge/decoy-{self.record.id}",
            plan=plan, reports=(self.report,),
            policy=PathPolicy.from_settings(self.settings), expires_at=None,
        )
        self.dep.set_preview(self.record, preview, contents)
        self.repo = resolve_repo(self.org, self.repo_id, "main")
        self.client.register_repo(self.repo, base_sha=_BASE)
        self.svc = DeploymentService(self.dep, self.art, self.client, self.settings)

    def to_deploying(self) -> None:
        for target in (
            DeploymentStatus.AWAITING_APPROVAL,
            DeploymentStatus.APPROVED,
            DeploymentStatus.DEPLOYING,
        ):
            self.dep.transition(self.record, target)


def _ctx(path: str = "docs/decoys/runbook.md") -> _Ctx:
    return _Ctx(sessionmaker(bind=_engine(), expire_on_commit=False)(), path)


def test_monitoring_not_activated_before_merge() -> None:
    c = _ctx()
    c.to_deploying()
    c.svc.execute(c.org, c.record.id)
    c.session.commit()
    assert c.record.pull_request_number is not None
    assert c.record.status == DeploymentStatus.DEPLOYING.value
    assert c.dep.active_tripwires(c.record.id) == ()  # no monitoring before merge


def test_monitoring_activates_after_verified_merge() -> None:
    c = _ctx()
    c.to_deploying()
    c.svc.execute(c.org, c.record.id)
    c.client.merge_pull_request(c.repo, c.record.pull_request_number)
    c.svc.verify(c.org, c.record.id)
    c.session.commit()
    assert c.record.status == DeploymentStatus.DEPLOYED.value
    assert c.record.monitoring_activated_at is not None
    assert len(c.dep.active_tripwires(c.record.id)) == 1


def test_closed_unmerged_pr_does_not_activate() -> None:
    c = _ctx()
    c.to_deploying()
    c.svc.execute(c.org, c.record.id)
    c.client.close_pull_request(c.repo, c.record.pull_request_number)
    c.svc.verify(c.org, c.record.id)
    c.session.commit()
    assert c.record.status == DeploymentStatus.CANCELLED.value
    assert c.dep.active_tripwires(c.record.id) == ()


def test_base_drift_blocks_deployment() -> None:
    c = _ctx()
    c.to_deploying()
    c.client.set_branch_sha(c.repo, "main", "moved999")  # base moved after approval
    c.svc.execute(c.org, c.record.id)
    c.session.commit()
    assert c.record.status == DeploymentStatus.FAILED.value
    assert c.record.failure_code == "base_changed"
    assert c.record.pull_request_number is None  # nothing written


def test_duplicate_job_does_not_create_second_pr() -> None:
    c = _ctx()
    first = c.dep.enqueue_job(
        organization_id=c.org, deployment_id=c.record.id, job_type="execute", correlation_id="a"
    )
    second = c.dep.enqueue_job(
        organization_id=c.org, deployment_id=c.record.id, job_type="execute", correlation_id="b"
    )
    c.session.commit()
    assert first is True and second is False  # one execute job per deployment


def test_verification_mismatch_fails_safely() -> None:
    c = _ctx()
    c.to_deploying()
    c.svc.execute(c.org, c.record.id)
    # Merge, then corrupt the merged tree so the deployed content no longer matches the preview.
    merge_sha = c.client.merge_pull_request(c.repo, c.record.pull_request_number)
    state = c.client._repos[(c.repo.owner, c.repo.name)]
    state.commits[merge_sha] = {"docs/decoys/runbook.md": "x"}
    c.svc.verify(c.org, c.record.id)
    c.session.commit()
    assert c.record.status == DeploymentStatus.VERIFICATION_FAILED.value
    assert c.dep.active_tripwires(c.record.id) == ()


def test_retirement_removes_only_owned_files_and_disables_monitoring() -> None:
    c = _ctx()
    c.to_deploying()
    c.svc.execute(c.org, c.record.id)
    c.client.merge_pull_request(c.repo, c.record.pull_request_number)
    c.svc.verify(c.org, c.record.id)
    # An unrelated user file exists on the default branch and must survive retirement.
    c.client.commit_files(c.repo, "main", {"docs/user_owned.md": "keep me"}, "user change")
    c.dep.transition(c.record, DeploymentStatus.RETIRING)
    c.svc.retire(c.org, c.record.id)
    assert c.dep.active_tripwires(c.record.id) == ()  # monitoring disabled at retire start
    c.client.merge_pull_request(c.repo, c.record.pull_request_number)
    c.svc.verify(c.org, c.record.id)
    c.session.commit()
    assert c.record.status == DeploymentStatus.RETIRED.value
    default_sha = c.client.get_branch(c.repo, "main").commit_sha
    tree = c.client.get_files_at(
        c.repo, default_sha, ("docs/decoys/runbook.md", "docs/user_owned.md")
    )
    assert "docs/decoys/runbook.md" not in tree  # decoy removed
    assert tree.get("docs/user_owned.md") == "keep me"  # user file preserved


def test_rollback_creates_revert_and_marks_rolled_back() -> None:
    c = _ctx()
    c.to_deploying()
    c.svc.execute(c.org, c.record.id)
    c.client.merge_pull_request(c.repo, c.record.pull_request_number)
    c.svc.verify(c.org, c.record.id)
    c.dep.transition(c.record, DeploymentStatus.ROLLBACK_PENDING)
    c.svc.rollback(c.org, c.record.id)
    c.client.merge_pull_request(c.repo, c.record.pull_request_number)
    c.svc.verify(c.org, c.record.id)
    c.session.commit()
    assert c.record.status == DeploymentStatus.ROLLED_BACK.value
    assert c.dep.active_tripwires(c.record.id) == ()


def test_cross_org_access_blocked() -> None:
    c = _ctx()
    with pytest.raises(DeploymentNotFoundError):
        c.dep.get(uuid4(), c.record.id)
