<!-- Purpose: document decoy deployment approval + the safe change-set/preview model. -->

# Decoy deployment

Turns accepted decoy generation plans into **reviewable, reversible** repository changes. Nothing is
written without human approval, and DeceptiForge never writes directly to the default branch.

Disabled by default. Enable per environment with `DECOY_DEPLOYMENT_ENABLED=true` (the API routes
mount only then). Repository-based decoys only (docs/runbooks/inert config/synthetic references/
safe secret-shaped tripwires). No database/spreadsheet/browser/RAG/MCP/agent deployment.

## Approval workflow

```
draft ──submit──▶ awaiting_approval ──approve──▶ approved ──deploy──▶ deploying ──verify──▶ deployed
                        │                                                   │
                     reject                                          verification_failed
                        ▼                                            deployed_unmonitored
                     rejected                                                │
deployed ──retire──▶ retiring ──▶ retired      deployed ──rollback──▶ rollback_pending ──▶ rolled_back
```

The full closed state machine lives in `app/models/domain/deployment.py`; illegal transitions are
rejected (`409`). A `failed` deployment can only re-enter through re-approval, never straight to
`deployed`.

### Permissions (scopes)

`decoy_deployments:{read,create,approve,execute,retire,rollback}`. Roles: viewer read; analyst
create; admin/owner full; service execute-only. **Separation of duties**: with
`REQUIRE_SEPARATE_DEPLOYMENT_APPROVER=true` (default) the requester cannot approve their own
deployment.

## Deployment preview (exact change set)

Generated before any write and stored with the deployment. Contains: target repo, base branch +
commit SHA, per-file unified diff, decoy types, trace IDs, validation decision, collision result,
expected monitoring registration, expiry, rollback strategy, warnings, changed files/bytes, blast
radius, and a `preview_hash`. The change-set content is **rendered inert** from decoy metadata —
synthetic values only, an ownership marker, and the trace. Raw secrets and raw payload bodies are
never included.

## Safety checks (re-run immediately before writing)

A deployment proceeds only when, for each asset: an accepted validation report exists, the target
path passes the policy, no production-name collision exists, the decoy is inert
(no real credentials/customer data, no auth capability), and the trace is valid. Path policy
(`app/services/deployment/policy.py`): allowlisted prefixes only
(`DECOY_ALLOWED_PATH_PREFIXES`), protected patterns rejected (`DECOY_PROTECTED_PATH_PATTERNS` — env
files, secrets, keys, lockfiles, `.github/workflows/`, …), plus traversal/absolute/home/binary/
executable rejection and `DECOY_MAX_FILES_PER_DEPLOYMENT` / `DECOY_MAX_BYTES_PER_DEPLOYMENT`
ceilings.

## API

`POST /decoy-deployments` (create + preview) · `GET /decoy-deployments` · `GET /{id}` ·
`GET /{id}/preview` · `GET /{id}/audit` · `POST /{id}/{submit,approve,reject,deploy,retire,rollback}`.
Every endpoint requires organization context + the matching scope, enforces the state machine,
returns sanitized errors with a `request_id`, and writes an audit event.

## Audit

Append-only per deployment: created, preview_generated, submitted, approved/rejected,
deployment_started, branch_created, commit_pushed, pr_created, verification_passed/failed,
monitoring_activated/failed, retirement/rollback started/completed, permission_denied,
stale_preview_detected. Never logs installation tokens, monitor secrets, full synthetic secret
values, raw repository contents, or credentialed Git URLs.

## Limitations

The live GitHub App adapter (installation tokens, git data API, webhooks) is **not implemented** in
this milestone — see `docs/integrations/GitHub.md`. All deployment logic is exercised against an
in-memory fake adapter. This is not full production certification.
