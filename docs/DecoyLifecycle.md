<!-- Purpose: document decoy deployment verification, monitoring activation, expiry/rotation/
retirement, rollback, drift, and failed-activation incident response. -->

# Decoy deployment lifecycle

## Monitoring activation (only after a verified merge)

DeceptiForge opens a pull request and **never merges automatically**. Tripwires activate only after
a human merges and verification passes:

1. Poll/receive the PR merge.
2. Fetch the merged commit; verify every expected file exists and its content hash matches the
   approved change set; confirm no unexpected files changed.
3. **Only then** register tripwires transactionally (persisted per deployment + trace + commit SHA,
   unique so activation is idempotent) and mark the deployment `deployed`.

If the PR is closed without merging → `cancelled`, no activation. If verification fails →
`verification_failed`, no activation.

### Failed activation — incident response

If the merge verified but tripwire registration was incomplete, the deployment is marked
`deployed_unmonitored` (never silently "deployed"), a **high-priority** metric
`deployment_monitoring_activation_failed` is emitted, and an audit event is written. Response:
investigate the registry, then either re-run activation or **roll back** the deployment. Do not
treat `deployed_unmonitored` as success — the decoy files are live but untripwired.

## Repository drift

Between preview and deployment the base branch may move. Before writing, the executor re-fetches the
base commit; if it changed, the deployment fails with `base_changed` and requires re-approval
(`preview_stale` / `reapproval_required`). A stale patch is never applied automatically.

## Expiry and rotation

Each deployment carries `expires_at` (`DECOY_DEFAULT_EXPIRY_DAYS`). Expiry and rotation are lifecycle
transitions; rotation retires the current decoy and creates a fresh deployment rather than editing
in place.

## Retirement (removal via PR)

Retirement also goes through a branch + pull request — the default branch is never edited directly.
Monitoring is disabled at retirement start (no active registry entries remain). The removal commit
deletes **only deployment-owned files** (matched by target path + ownership marker + content hash),
so unrelated user changes to shared files are preserved. After the removal PR merges and removal is
verified, the deployment becomes `retired`.

## Rollback

For an invalid change, failed activation, an accidental merge, or emergency retirement:

1. Generate a rollback preview; require authorization.
2. Create a rollback branch; revert only deployment-owned changes.
3. Open a rollback PR (never force-push, never rewrite history).
4. Disable monitoring at the policy point.
5. After the PR merges and removal is verified → `rolled_back`.

## Asynchronous jobs

`execute`, `verify`, `retire`, and `rollback` run off the request path via the deployment work queue
(`deployment_jobs`, unique per deployment + type). Jobs claim atomically, are idempotent, and a
duplicate deploy request never creates a second PR. Worker entrypoint: `python -m app.jobs.deployment`
(refuses to run until a live adapter is wired — see `docs/integrations/GitHub.md`).
