<!-- Purpose: document the DeceptiForge security model. Responsibilities: auth, API keys, monitor
ingest identity, permissions, replay, audit, and honest limitations. -->

# Security model

**Status: controlled-staging grade, not full production SaaS.** This is a scoped API-key model, not
user identity / OAuth / SSO / full RBAC.

## Authentication

`require_org` / `require_scope` resolve the caller:

- `AUTH_ENABLED=false` is honored **only in `APP_ENV=development`** (bypass to the demo org). In any
  other environment a disabled auth flag is rejected (`401`).
- Otherwise an API key is required. Keys are **hashed** (SHA-256) and stored as `key_hash` +
  `key_prefix`; the plaintext is shown once at creation and never stored or logged.
- Each key is bound to exactly one organization. A mismatching `X-DeceptiForge-Org-Id` → `403`. One
  shared key cannot act as an arbitrary organization.
- Key status: `active` / `revoked`; optional `expires_at`; `last_used_at` is updated on use.
- `API_KEY_BINDINGS` (env JSON) is a **bootstrap/service** path (owner scope) to mint the first admin
  key; prefer DB-backed hashed keys for tenants.

## Roles and permissions

Roles: `owner`, `admin`, `analyst`, `viewer`, `service`. Permissions are `resource:action` scopes
(e.g. `repositories:write`, `monitoring:ingest`, `admin:manage_keys`). Endpoints enforce the exact
scope; a `viewer` cannot write, a read-only tenant key cannot ingest monitoring events.

Admin: `POST/GET/DELETE /admin/api-keys` (scope `admin:manage_keys`).

## Monitoring ingest identity + replay

`POST /monitoring/events` requires the `monitoring:ingest` scope (a `service` key). When auth is
enabled it also requires `X-DeceptiForge-Nonce` and `X-DeceptiForge-Timestamp`; nonces are single-use
within a window and timestamps must be within the configured clock skew. Oversized values are
rejected (413) before any matching/hashing/persistence.

Limitation: nonce store and rate limiter are **in-process** (single worker). Production needs a
shared store (Redis) and/or an edge gateway. Signed monitor request bodies are future work.

## Audit

`security_audit` records auth/authz outcomes, key create/revoke, and cross-org attempts with a
`request_id`. It never stores secrets or raw payloads.

## Data handling

- GPT receives only sanitized, bounded context; it can never mutate deterministic incident facts.
- Error responses never leak stack traces, filesystem paths, SQL, provider details, raw payloads, or
  keys; each carries `x-request-id`.
- Artifact JSON blobs are size-capped before persistence; narrative revisions are pruned to a
  retention count. Application-layer encryption and full retention jobs are **future work**.

## Not implemented (still required for production)

Real identity/OAuth/SSO, full RBAC and key rotation, per-request signing, distributed rate limiting
and replay store, async/durable ingestion, field-level encryption, and scheduled retention.

## Decoy deployment (approval + lifecycle)

Deploying decoys to repositories is gated by human approval and a closed state machine (see
`docs/DecoyDeployment.md`, `docs/DecoyLifecycle.md`). Invariants: no direct default-branch writes; no
automatic merge; monitoring activates only after a **verified merge**; retire/rollback go through
PRs and remove only deployment-owned content; every action is organization-scoped, scope-checked
(`decoy_deployments:*`), separation-of-duties-guarded, and audited. Rendered decoy content is inert
(synthetic values only). The feature is disabled by default (`DECOY_DEPLOYMENT_ENABLED`). The live
GitHub App adapter is not implemented — `docs/integrations/GitHub.md`.
