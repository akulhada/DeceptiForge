# Purpose: orchestrate the safe GitHub deployment lifecycle for approved decoy deployments.
# Responsibilities: execute (branch + commit + PR, never merge), verify a merged PR and only then
#   activate monitoring, and retire/rollback via removal/revert PRs. Re-runs safety and drift checks
#   immediately before writing, keeps every step organization-scoped and audited, and never persists
#   or logs tokens. Dependencies: DeploymentRepository, ArtifactRepository, the client port, policy,
#   preview, and settings.
from __future__ import annotations

import hashlib
from uuid import UUID

from app.config.settings import Settings
from app.models.domain.deployment import DeploymentStatus
from app.repositories.artifacts import ArtifactRepository
from app.repositories.deployments import DeploymentRepository
from app.services.deployment.github_port import (
    DeploymentClientError,
    RepoRef,
    RepositoryDeploymentClient,
)
from app.services.deployment.policy import PathPolicy
from app.services.deployment.safety import evaluate
from app.services.metrics import emit

_BRANCH_PREFIX = "deceptiforge/decoy-"


def resolve_repo(
    organization_id: UUID, repository_id: UUID, default_branch: str = "main"
) -> RepoRef:
    """Deterministic RepoRef for a repository. A real GitHub App adapter would resolve the
    installation + repo here; the fake adapter is seeded with the same ref."""
    return RepoRef(
        owner=f"org-{organization_id}", name=str(repository_id), default_branch=default_branch
    )


class DeploymentService:
    def __init__(
        self,
        deployments: DeploymentRepository,
        artifacts: ArtifactRepository,
        client: RepositoryDeploymentClient,
        settings: Settings,
        *,
        request_id: str = "worker",
    ) -> None:
        self._d = deployments
        self._a = artifacts
        self._client = client
        self._settings = settings
        self._request_id = request_id

    # -- execute (branch + commit + PR; never merges) -----------------------------------------

    def execute(self, organization_id: UUID, deployment_id: UUID) -> None:
        record = self._d.get(organization_id, deployment_id)
        if record.status != DeploymentStatus.DEPLOYING.value:
            return  # only a deploying record is executed
        preview = self._d.load_preview(record)
        if preview is None:
            self._fail(record, "no_preview", "deployment has no preview")
            return

        # Re-run safety immediately before writing.
        if not self._resafe(record):
            self._fail(record, "safety_failed", "safety re-check failed before write")
            return

        repo = resolve_repo(organization_id, record.repository_id, preview.base_branch)
        try:
            # Drift: refuse if the base branch moved since the preview was approved.
            current = self._client.get_branch(repo, preview.base_branch).commit_sha
            if current != record.base_commit_sha:
                self._d.add_audit(
                    organization_id=organization_id, deployment_id=deployment_id,
                    actor_id=None, event_type="stale_preview_detected", request_id=self._request_id,
                )
                self._fail(record, "base_changed", "base branch changed; re-approval required")
                return

            # Idempotent: if a PR already exists, do not open a second one.
            if record.pull_request_number is not None:
                return

            branch = f"{_BRANCH_PREFIX}{deployment_id}"
            self._client.create_branch(repo, branch, record.base_commit_sha)
            self._d.add_audit(
                organization_id=organization_id, deployment_id=deployment_id, actor_id=None,
                event_type="branch_created", request_id=self._request_id, safe_metadata=branch,
            )
            files = {
                item.target_path: item.content_data
                for item in self._d.get_items(deployment_id)
            }
            self._client.commit_files(repo, branch, files, self._commit_message(deployment_id))
            self._d.add_audit(
                organization_id=organization_id, deployment_id=deployment_id, actor_id=None,
                event_type="commit_pushed", request_id=self._request_id,
            )
            pr = self._client.open_pull_request(
                repo, branch, preview.base_branch,
                "chore(security): add DeceptiForge decoy assets",
                self._pr_body(deployment_id, preview.trace_identifiers),
            )
            record.pull_request_number = pr.number
            record.pull_request_url = pr.url
            record.source_branch = branch
            self._d.add_audit(
                organization_id=organization_id, deployment_id=deployment_id, actor_id=None,
                event_type="pr_created", request_id=self._request_id,
                safe_metadata=f"pr={pr.number}",
            )
            self._d._session.flush()
        except DeploymentClientError as error:
            self._fail(record, "provider_error", str(error))

    # -- verify (only after a confirmed merge; then activate monitoring) ----------------------

    def verify(self, organization_id: UUID, deployment_id: UUID) -> None:
        record = self._d.get(organization_id, deployment_id)
        status = DeploymentStatus(record.status)
        if record.pull_request_number is None:
            return
        repo = resolve_repo(organization_id, record.repository_id)
        pr = self._client.get_pull_request(repo, record.pull_request_number)

        if pr.state == "closed" and not pr.merged:
            # Closed without merge: cancel and never activate monitoring.
            self._d.transition(record, DeploymentStatus.CANCELLED)
            self._d.add_audit(
                organization_id=organization_id, deployment_id=deployment_id, actor_id=None,
                event_type="pr_closed_unmerged", request_id=self._request_id,
            )
            return
        if not pr.merged or pr.merge_commit_sha is None:
            return  # still open; a later verify pass handles the merge

        if status is DeploymentStatus.DEPLOYING:
            self._verify_deploy(organization_id, record, repo, pr.merge_commit_sha)
        elif status is DeploymentStatus.RETIRING:
            self._verify_removal(organization_id, record, repo, pr.merge_commit_sha,
                                 DeploymentStatus.RETIRED, "retirement")
        elif status is DeploymentStatus.ROLLBACK_PENDING:
            self._verify_removal(organization_id, record, repo, pr.merge_commit_sha,
                                 DeploymentStatus.ROLLED_BACK, "rollback")

    def _verify_deploy(self, org: UUID, record, repo: RepoRef, merge_sha: str) -> None:  # type: ignore[no-untyped-def]
        items = self._d.get_items(record.id)
        paths = tuple(item.target_path for item in items)
        merged = self._client.get_files_at(repo, merge_sha, paths)
        for item in items:
            content = merged.get(item.target_path)
            if content is None or _sha(content) != item.proposed_content_hash:
                self._d.transition(
                    record, DeploymentStatus.VERIFICATION_FAILED,
                    failure_code="verify_mismatch",
                    safe_failure_message="merged files did not match the approved change set",
                )
                self._d.add_audit(
                    organization_id=org, deployment_id=record.id, actor_id=None,
                    event_type="verification_failed", request_id=self._request_id,
                )
                return
            item.deployed_content_hash = item.proposed_content_hash
            item.status = "verified"
        self._d.add_audit(
            organization_id=org, deployment_id=record.id, actor_id=None,
            event_type="verification_passed", request_id=self._request_id,
        )
        # Verified: activate monitoring transactionally, only now.
        preview = self._d.load_preview(record)
        change_items = preview.items if preview else ()
        activated = self._d.activate_tripwires(
            organization_id=org, deployment_id=record.id, items=change_items, commit_sha=merge_sha
        )
        active = len(self._d.active_tripwires(record.id))
        from datetime import UTC, datetime

        now = datetime.now(UTC)
        if active == len(change_items) and active > 0:
            self._d.transition(
                record, DeploymentStatus.DEPLOYED, deployed_commit_sha=merge_sha,
                deployed_at=now, monitoring_activated_at=now,
            )
            self._d.add_audit(
                organization_id=org, deployment_id=record.id, actor_id=None,
                event_type="monitoring_activated", request_id=self._request_id,
                safe_metadata=f"traces={active}",
            )
        else:
            self._d.transition(
                record, DeploymentStatus.DEPLOYED_UNMONITORED, deployed_commit_sha=merge_sha,
                deployed_at=now, failure_code="activation_failed",
                safe_failure_message="deployment merged but monitoring activation was incomplete",
            )
            emit(
                "deployment_monitoring_activation_failed", severity="high",
                deployment_id=str(record.id), organization_id=str(org),
                expected=len(change_items), activated=activated,
            )
            self._d.add_audit(
                organization_id=org, deployment_id=record.id, actor_id=None,
                event_type="monitoring_activation_failed", request_id=self._request_id,
            )

    def _verify_removal(  # type: ignore[no-untyped-def]
        self, org: UUID, record, repo: RepoRef, merge_sha: str,
        terminal: DeploymentStatus, kind: str,
    ) -> None:
        # Confirm the deployment-owned files are gone at the merged commit.
        items = self._d.get_items(record.id)
        paths = tuple(item.target_path for item in items)
        remaining = self._client.get_files_at(repo, merge_sha, paths)
        if remaining:
            self._d.add_audit(
                organization_id=org, deployment_id=record.id, actor_id=None,
                event_type=f"{kind}_verification_failed", request_id=self._request_id,
            )
            return
        from datetime import UTC, datetime

        self._d.transition(record, terminal, retired_at=datetime.now(UTC))
        for item in items:
            item.status = "retired" if terminal is DeploymentStatus.RETIRED else "rolled_back"
        self._d.add_audit(
            organization_id=org, deployment_id=record.id, actor_id=None,
            event_type=f"{kind}_completed", request_id=self._request_id,
        )

    # -- retire / rollback (removal + revert PRs; disable monitoring) --------------------------

    def retire(self, organization_id: UUID, deployment_id: UUID) -> None:
        self._open_removal(organization_id, deployment_id, "retire", "retired")

    def rollback(self, organization_id: UUID, deployment_id: UUID) -> None:
        self._open_removal(organization_id, deployment_id, "rollback", "disabled")

    def _open_removal(
        self, organization_id: UUID, deployment_id: UUID, kind: str, tripwire_status: str
    ) -> None:
        record = self._d.get(organization_id, deployment_id)
        expected = (
            DeploymentStatus.RETIRING if kind == "retire" else DeploymentStatus.ROLLBACK_PENDING
        )
        if record.status != expected.value:
            return
        # Disable monitoring at the lifecycle policy point: no active registry entries remain.
        self._d.set_tripwire_status(deployment_id, tripwire_status)
        self._d.add_audit(
            organization_id=organization_id, deployment_id=deployment_id, actor_id=None,
            event_type=f"{kind}_started", request_id=self._request_id,
        )
        repo = resolve_repo(organization_id, record.repository_id)
        try:
            default = self._client.get_branch(repo, repo.default_branch).commit_sha
            branch = f"deceptiforge/{kind}-{deployment_id}"
            self._client.create_branch(repo, branch, default)
            removed = tuple(item.target_path for item in self._d.get_items(deployment_id))
            self._client.commit_files(
                repo, branch, {}, f"chore(security): {kind} DeceptiForge decoys", removed
            )
            pr = self._client.open_pull_request(
                repo, branch, repo.default_branch,
                f"chore(security): {kind} DeceptiForge decoy assets",
                f"Automated {kind} of deployment {deployment_id}. Removes only decoy-owned files.",
            )
            record.pull_request_number = pr.number
            record.pull_request_url = pr.url
            record.source_branch = branch
            self._d.add_audit(
                organization_id=organization_id, deployment_id=deployment_id, actor_id=None,
                event_type="pr_created", request_id=self._request_id,
                safe_metadata=f"pr={pr.number}",
            )
            self._d._session.flush()
        except DeploymentClientError as error:
            self._d.transition(record, DeploymentStatus.FAILED, failure_code="provider_error",
                              safe_failure_message=str(error)[:512])

    # -- helpers ------------------------------------------------------------------------------

    def _resafe(self, record) -> bool:  # type: ignore[no-untyped-def]
        loaded = self._a.get_decoy_plan(record.organization_id, record.decoy_plan_id)
        if loaded is None:
            return False
        _, plan = loaded
        reports = self._a.reports_for_decoy_plan(record.organization_id, record.decoy_plan_id)
        policy = PathPolicy.from_settings(self._settings)
        return evaluate(plan, reports, policy).any_deployable

    def _fail(self, record, code: str, message: str) -> None:  # type: ignore[no-untyped-def]
        self._d.transition(
            record, DeploymentStatus.FAILED, failure_code=code, safe_failure_message=message[:512]
        )
        self._d.add_audit(
            organization_id=record.organization_id, deployment_id=record.id, actor_id=None,
            event_type="deployment_failed", request_id=self._request_id, safe_metadata=code,
        )

    def _commit_message(self, deployment_id: UUID) -> str:
        return f"chore(security): add DeceptiForge decoy assets ({deployment_id})"

    def _pr_body(self, deployment_id: UUID, traces: tuple[str, ...]) -> str:
        level = self._settings.decoy_pr_detail_level
        lines = [
            f"Deployment: {deployment_id}",
            "Synthetic, inert decoy assets from DeceptiForge. No real secrets or credentials.",
            "Safety validation: accepted. Monitoring activates only after this PR is merged.",
            "Rollback: revert only decoy-owned files via an automated rollback PR.",
        ]
        if level == "full":
            lines.append(f"Traces: {len(traces)} tripwire markers.")
        lines.append("Reviewer checklist: [ ] paths expected  [ ] content inert  [ ] no real data")
        return "\n".join(lines)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
