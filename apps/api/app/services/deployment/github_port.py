# Purpose: define the repository-deployment port and an in-memory fake adapter.
# Responsibilities: express the exact GitHub operations the deployment flow needs (base metadata,
#   branch, commit, pull request, merge status, merged-file readback) without binding to a real
#   provider. The live GitHub App adapter (JWT app auth, short-lived installation tokens, git data
#   API, webhooks) is intentionally NOT implemented here and must never persist tokens. The fake
#   adapter is deterministic, network-free, and token-free — used for development and tests.
# Dependencies: stdlib only.
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class RepoRef:
    owner: str
    name: str
    default_branch: str


@dataclass(frozen=True)
class BranchInfo:
    name: str
    commit_sha: str


@dataclass(frozen=True)
class PullRequestInfo:
    number: int
    url: str
    state: str  # "open" | "closed"
    merged: bool
    merge_commit_sha: str | None


class DeploymentClientError(Exception):
    """Raised for provider-side failures. Messages are safe (no tokens, no raw content)."""


class RepositoryDeploymentClient(Protocol):
    """The operations the deployment flow needs. Writes go to a dedicated branch + PR, never the
    default branch; nothing is ever merged automatically."""

    def get_branch(self, repo: RepoRef, branch: str) -> BranchInfo: ...

    def create_branch(self, repo: RepoRef, new_branch: str, base_sha: str) -> BranchInfo: ...

    def commit_files(
        self,
        repo: RepoRef,
        branch: str,
        files: dict[str, str],
        message: str,
        removed_paths: tuple[str, ...] = (),
    ) -> str: ...

    def open_pull_request(
        self, repo: RepoRef, head: str, base: str, title: str, body: str
    ) -> PullRequestInfo: ...

    def get_pull_request(self, repo: RepoRef, number: int) -> PullRequestInfo: ...

    def get_files_at(
        self, repo: RepoRef, commit_sha: str, paths: tuple[str, ...]
    ) -> dict[str, str]: ...


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass
class _FakeRepoState:
    default_branch: str
    # branch -> commit sha; commit sha -> {path: content}
    branches: dict[str, str] = field(default_factory=dict)
    commits: dict[str, dict[str, str]] = field(default_factory=dict)
    pulls: dict[int, PullRequestInfo] = field(default_factory=dict)
    pr_head: dict[int, str] = field(default_factory=dict)
    next_pr: int = 1


class FakeDeploymentClient:
    """Deterministic in-memory adapter. No network, no tokens. Test hooks: merge_pull_request,
    close_pull_request, and set_branch_sha (to simulate drift)."""

    def __init__(self) -> None:
        self._repos: dict[tuple[str, str], _FakeRepoState] = {}

    def register_repo(self, repo: RepoRef, base_sha: str = "base0000") -> None:
        state = _FakeRepoState(default_branch=repo.default_branch)
        state.branches[repo.default_branch] = base_sha
        state.commits[base_sha] = {}
        self._repos[(repo.owner, repo.name)] = state

    def _state(self, repo: RepoRef) -> _FakeRepoState:
        state = self._repos.get((repo.owner, repo.name))
        if state is None:
            raise DeploymentClientError("repository/installation not resolved")
        return state

    def get_branch(self, repo: RepoRef, branch: str) -> BranchInfo:
        state = self._state(repo)
        if branch not in state.branches:
            raise DeploymentClientError("branch not found")
        return BranchInfo(name=branch, commit_sha=state.branches[branch])

    def create_branch(self, repo: RepoRef, new_branch: str, base_sha: str) -> BranchInfo:
        state = self._state(repo)
        if base_sha not in state.commits:
            raise DeploymentClientError("base commit not found")
        # Idempotent: recreating an existing branch at the same base is a no-op, so a retried job
        # does not fail or fork history.
        state.branches[new_branch] = base_sha
        return BranchInfo(name=new_branch, commit_sha=base_sha)

    def commit_files(
        self,
        repo: RepoRef,
        branch: str,
        files: dict[str, str],
        message: str,
        removed_paths: tuple[str, ...] = (),
    ) -> str:
        state = self._state(repo)
        if branch not in state.branches:
            raise DeploymentClientError("branch not found")
        parent = state.branches[branch]
        tree = dict(state.commits.get(parent, {}))
        tree.update(files)
        for path in removed_paths:
            tree.pop(path, None)
        commit_sha = _sha(f"{parent}:{message}:" + ":".join(sorted(tree)))
        state.commits[commit_sha] = tree
        state.branches[branch] = commit_sha
        return commit_sha

    def open_pull_request(
        self, repo: RepoRef, head: str, base: str, title: str, body: str
    ) -> PullRequestInfo:
        state = self._state(repo)
        number = state.next_pr
        state.next_pr += 1
        pr = PullRequestInfo(
            number=number,
            url=f"https://example.invalid/{repo.owner}/{repo.name}/pull/{number}",
            state="open",
            merged=False,
            merge_commit_sha=None,
        )
        state.pulls[number] = pr
        state.pr_head[number] = head
        return pr

    def get_pull_request(self, repo: RepoRef, number: int) -> PullRequestInfo:
        state = self._state(repo)
        if number not in state.pulls:
            raise DeploymentClientError("pull request not found")
        return state.pulls[number]

    def get_files_at(
        self, repo: RepoRef, commit_sha: str, paths: tuple[str, ...]
    ) -> dict[str, str]:
        state = self._state(repo)
        tree = state.commits.get(commit_sha)
        if tree is None:
            raise DeploymentClientError("commit not found")
        return {path: tree[path] for path in paths if path in tree}

    # ---- test hooks (simulate the human/GitHub side; not part of the port) ----------------------

    def merge_pull_request(self, repo: RepoRef, number: int) -> str:
        state = self._state(repo)
        pr = state.pulls[number]
        head = state.pr_head[number]
        merge_sha = state.branches[head]
        state.branches[state.default_branch] = merge_sha  # merge into default
        state.pulls[number] = PullRequestInfo(
            number=number, url=pr.url, state="closed", merged=True, merge_commit_sha=merge_sha
        )
        return merge_sha

    def close_pull_request(self, repo: RepoRef, number: int) -> None:
        state = self._state(repo)
        pr = state.pulls[number]
        state.pulls[number] = PullRequestInfo(
            number=number, url=pr.url, state="closed", merged=False, merge_commit_sha=None
        )

    def set_branch_sha(self, repo: RepoRef, branch: str, sha: str) -> None:
        state = self._state(repo)
        state.commits.setdefault(sha, {})
        state.branches[branch] = sha
