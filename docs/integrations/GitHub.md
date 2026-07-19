<!-- Purpose: document the repository-deployment port, the branch/PR strategy, the GitHub App
permissions a real adapter needs, and the current implementation status. -->

# GitHub integration (repository deployment)

## Status

The **live GitHub App adapter is not implemented** in this milestone. DeceptiForge defines a
provider-neutral port, `RepositoryDeploymentClient`
(`app/services/deployment/github_port.py`), and ships a deterministic, network-free, token-free
`FakeDeploymentClient` used for development and tests. All deployment/approval/lifecycle logic runs
against that fake. The worker entrypoint (`python -m app.jobs.deployment`) refuses to run until a
real adapter is wired, so it can never silently no-op in production.

> Note: real-repository *scanning* (async, sandboxed GitHub scan jobs) is likewise not implemented;
> repository scanning today is local-filesystem and **development-only**.

## The port

```
get_branch(repo, branch) -> BranchInfo            # base metadata + drift check
create_branch(repo, new_branch, base_sha)         # dedicated branch, never the default
commit_files(repo, branch, files, message, removed_paths=())
open_pull_request(repo, head, base, title, body) -> PullRequestInfo   # never merged automatically
get_pull_request(repo, number) -> PullRequestInfo # merge status
get_files_at(repo, commit_sha, paths) -> files    # post-merge verification
```

## Branch / PR strategy

- Deploy branch: `deceptiforge/decoy-{deployment_id}`; retire/rollback branches:
  `deceptiforge/{retire,rollback}-{deployment_id}`.
- Deterministic commit message; PR title `chore(security): add DeceptiForge decoy assets`.
- The PR body declares the synthetic/inert nature, safety result, expiry, rollback instructions, a
  monitoring-activation note, and a reviewer checklist. Detail level is configurable
  (`DECOY_PR_DETAIL_LEVEL`) so defensive detection logic is not over-disclosed on public repos.
- **No automatic merge.** Monitoring activates only after a human merges and verification passes.

## What a real adapter must do

- Authenticate as a GitHub App (JWT), then request **short-lived installation tokens** per operation.
  Tokens are used in-memory and **never persisted or logged**.
- Implement the port over the GitHub REST/GraphQL git data API (refs, blobs/trees or contents,
  pulls).
- Receive PR `merged`/`closed` webhooks (or poll) and enqueue `verify` jobs.
- Minimum permissions: Contents (read/write), Pull requests (read/write), Metadata (read). No admin,
  no workflow-file write (`.github/workflows/` is a protected path anyway).

## Safety invariants the adapter must preserve

Never write the default branch directly; never merge automatically; never execute repository code;
never write real secrets or valid credentials; remove only deployment-owned content on retire/
rollback; keep every operation organization-scoped and audited.
