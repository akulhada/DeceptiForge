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

## Database honey records (PostgreSQL)

Synthetic honey rows are inserted into approved customer tables as tripwires (see
`docs/DatabaseHoneyRecords.md`, `docs/DatabaseDeploymentSafety.md`, `docs/integrations/PostgreSQL.md`).
Invariants: no arbitrary SQL; least-privilege TLS connections; strict table allowlist + sensitivity/
trigger/FK rejection; deterministic synthetic-only data (no real PII/payment/credentials); human
approval + separation of duties; transactional insert with monitoring activated only after
verification; retire/rollback delete only the exact owned row (drift blocks deletion); connector
secrets encrypted at rest and never returned. Disabled by default.

## AI tripwires (RAG / MCP)

Inert synthetic decoy documents (RAG) and resources/configs (MCP) are deployed into approved
collections/servers as tripwires (see `docs/AiTripwires.md`, `docs/AiDataHandling.md`,
`docs/integrations/RAG.md`, `docs/integrations/MCP.md`). Invariants: every asset inert (no real
data/credentials/URLs, no executable payloads, no prompt injection); content safety validates before
preview; collection/server allowlists; human approval + separation of duties; deploy through an
adapter, verify the external asset + trace, and **activate monitoring only after verification**;
retire deletes only the owned asset (drift blocks deletion); event ingestion is signed + replay-
protected and **minimized** — never storing/logging prompts, chunks, model output, raw embeddings,
connector secrets, or raw customer content; deterministic exposure classification + severity (GPT
never decides safety or severity). Connector secrets encrypted at rest and never returned. Disabled
by default.

## Browser AI-paste sensor (Shadow AI)

A Chromium extension detects DeceptiForge trace markers pasted into AI tools (see
`docs/BrowserAiSensor.md`, `docs/ShadowAiDetection.md`, `docs/BrowserPrivacy.md`,
`docs/ExtensionDeployment.md`). Invariants: local matching against irreversible hashed trace tokens
(no full decoy payload or marker plaintext shipped); observe only explicit paste/beforeinput on
monitored AI domains — never password/payment/hidden fields, history, keystrokes, or clipboard;
never persist/transmit pasted text, prompts, or AI responses; per-install scoped credential (not a
dashboard key) provisioned via one-time short-lived enrollment tokens; `monitor-signature-v1` signed
+ replay-protected + minimized ingestion; server-side (not extension-trusted) destination
classification and deterministic exposure + severity with cross-surface correlation (GPT never
decides severity); revocation is terminal and revokes the scoped key; versioned policy with
downgrade rejection; minimal MV3 permissions (storage, alarms; host-scoped to AI domains), locked
CSP, no eval, no remote code. Secrets encrypted at rest and never returned. Disabled by default.

## AI agent activity sensor (scope violations)

Registered agent sessions report minimized, signed activity; deterministic rules raise explainable
scope violations and decoy-touch events (see `docs/AiAgentSensor.md`, `docs/AgentScopePolicies.md`,
`docs/AgentPrivacy.md`, `docs/AgentAdapterSDK.md`). Invariants: observe only registered sessions
under explicit policy; per-install scoped credential (not a dashboard key) via one-time enrollment
tokens; `monitor-signature-v1` signed + replay-protected + size-bounded + idempotent ingestion;
safe path normalization (rejects traversal/encoded/absolute/root-escape) before any policy check;
deterministic path classification, scope-violation rules, and incident severity — GPT explains but
never decides a violation or severity; decoy touch matched by metadata (no raw content); minimized
metadata only — never file contents, prompts, command output, model reasoning, terminal history, or
secrets; detect-only by default (blocking gated behind explicit policy); raw activity events expire
before violations/summaries; revocation terminal and revokes the scoped key. Secrets encrypted at
rest and never returned. Disabled by default.
