<!-- Purpose: honest production-readiness status after the master stabilization milestone. -->

# Production readiness

**Recommendation: controlled staging with a trusted reverse proxy and Redis/edge rate limiting —
not open multi-tenant production.** The system is materially safer than the hackathon MVP but is not
a finished SaaS.

## Now in place

- Authenticated tenant dashboard read path (no `/demo/*`); demo mode stays development-only.
- Hashed, scoped, revocable, expirable API keys bound to one organization; admin key endpoints;
  plaintext shown once, never logged. See [SecurityModel](SecurityModel.md).
- Monitoring ingest requires the `monitoring:ingest` scope plus nonce + timestamp (replay/skew
  protection); oversized payloads rejected before pipeline work.
- Episode-scoped incident identity (same trace in a later window is a new incident) and incident
  lifecycle (`open`→`stale`) with a non-destructive retirement function.
- Organization-scoped persistence and reads across the pipeline; incident upsert (no global
  delete/reinsert); cross-org access denied consistently.
- Rate-limit abstraction with a production config guard (production `app` mode requires `REDIS_URL`,
  else `RATE_LIMIT_MODE=gateway`).
- Request-id middleware, safe global error handling, CORS fail-closed (no wildcard/credentials),
  body/artifact size limits, non-root container without auto-migrations, private-network DB compose.

## Still staging-grade / MVP (do not oversell)

- Rate limiter and replay nonce store are **in-process** (single worker). Production needs Redis or
  an edge gateway; the config guard makes this explicit but the Redis backend is not implemented.
- `API_KEY_BINDINGS` env keys remain as a bootstrap path.
- Monitor identity is a scoped service key, not signed request bodies / a separate credential model.
- No application-layer encryption of JSON blobs; retention beyond narrative-revision pruning is a
  documented target, not a scheduled job.
- No real identity/OAuth/SSO/RBAC beyond role→scope, and no key rotation.
- Repository scanning stays local/development-only; provider integrations are future work.
- Frontend has API-client unit tests only; full component tests are future work.

## Operate

- Migrations run as a **separate** release step (never at container startup) — see
  [Deployment](Deployment.md).
- Preflight: [ProductionPreflight](checklists/ProductionPreflight.md).

## Database honey records

Disabled by default. When enabled, connector secrets are encrypted at rest, TLS is required outside
development, only approved non-sensitive tables receive rows, generated data is synthetic-only, and
retire/rollback delete only the exact owned row. The real connector adapter is validated in CI
against an ephemeral PostgreSQL with a synthetic schema — never customer data.

## AI tripwires (RAG / MCP)

Disabled by default. When enabled, connector secrets are encrypted at rest, TLS is required outside
development, only allowlisted collections/servers are targeted, deployed assets are inert and
synthetic-only, monitoring activates only after the external asset + trace are verified, and
retirement deletes only the owned asset (drift blocks deletion). Event ingestion is signed, replay-
protected, and minimized — no prompts, chunks, model output, raw embeddings, or raw customer content
are persisted. RAG/MCP coverage runs in CI against deterministic in-memory fake adapters; no paid
vector store or MCP server is contacted. Production wiring binds concrete provider clients.

## Browser AI-paste sensor

Disabled by default (`BROWSER_SENSOR_ENABLED`); explicit staging/production enablement required.
Per-install sensors are provisioned via one-time short-lived enrollment tokens with a scoped ingest
credential (never a dashboard key); event ingestion is signed + replay-protected + minimized (no
pasted text, prompts, or AI responses persisted). Matching is local against hashed trace tokens.
Revocation is terminal and revokes the scoped key. The extension requests minimal MV3 permissions
(storage, alarms; host-scoped to the supported AI domains) with a locked CSP. CI runs extension
typecheck/lint/unit-tests/production build plus a hardening audit that fails on any forbidden
permission, `eval`/`new Function`, remote script URL, or embedded secret. The extension is not
auto-published. A legal/privacy review is required before enterprise rollout.

## AI agent activity sensor

Disabled by default (`AGENT_SENSOR_ENABLED`), detect-only (`AGENT_SENSOR_MODE=detect`); explicit
staging/production enablement required. Per-install sensors are provisioned via one-time enrollment
tokens with a scoped ingest credential (never a dashboard key). Event ingestion is
`monitor-signature-v1` signed, replay-protected, size-bounded, and idempotent; only minimized
metadata is stored (no file contents, prompts, command output, or model reasoning). Paths are
safely normalized before policy checks; scope violations, path classes, and severity are
deterministic (GPT never decides). Blocking is disabled by default and gated behind explicit policy.
Raw activity events are retained for `AGENT_EVENT_RETENTION_DAYS` and expire before violations and
session summaries; cleanup is org-scoped, batched, scheduled, and auditable. CI exercises the
adapter/CLI contract, path-normalization safety, deterministic scope rules, and signed ingestion —
no third-party agent service is contacted.

## Measured coverage engine

Disabled by default (`COVERAGE_ENGINE_ENABLED`); explicit staging/production enablement required.
Coverage is deterministic and risk-weighted from real active controls; failed/expired controls earn
nothing, unknown inventory is reported separately (never counted as covered), and a high score with
low confidence is shown as qualified. Snapshots are immutable and idempotent by source-state hash,
so a scheduled or concurrent run over unchanged state creates nothing new. Add the coverage
calculation job to the deployment topology (`python -m app.jobs.coverage`) — organization-scoped,
advisory-locked, bounded, retryable; a manual recalculation is available to authorized users.
Recommendations are never auto-deployed. CI includes coverage unit + cross-surface tests, the
scheduled-job test, and a large-inventory performance regression guard.

## SIEM/SOAR export

Disabled by default (`SECURITY_INTEGRATIONS_ENABLED`); explicit staging/production enablement
required. Delivery is asynchronous via a transactional outbox (created in the same transaction as
the source alert/incident) and a lease-based delivery worker
(`python -m app.jobs.security_export`) — core ingestion never waits on an external SIEM and no export
is lost after a committed source. Credentials are encrypted at rest, decrypted only in the worker,
and never returned or logged. Endpoints are SSRF-validated (loopback/link-local/private/metadata
rejected; redirects disabled). Deliveries are idempotent, retried with backoff, and dead-lettered
deterministically; delivered payloads expire before the dead-letter hash records. CI runs the SSRF
security tests, adapter contract, and outbox/delivery concurrency tests against mock transports — no
real SIEM tenant is contacted. Add the delivery worker to the deployment topology; a dedicated
security-export worker service is recommended.

## Multi-region reliability & disaster recovery

Configure region identity (`DEPLOYMENT_REGION`, `CLUSTER_ROLE`, `ACTIVE_REGION_EPOCH`) — production
rejects ambiguous `CLUSTER_ROLE`. Only the primary region accepts writes and runs schedulers/side-
effect workers (retention, coverage, and the SIEM delivery worker skip on a non-leader region), so
no scheduler or external side effect runs in two regions. Readiness reflects safe operating capability
(database + encryption + mandatory replay). PostgreSQL backups must be automated + encrypted; a
backup is not valid until a restore drill passes (`/admin/reliability/restore-drills`,
`RESTORE_DRILL_ENABLED`) — the drill records the achieved RPO/RTO against the critical targets (≤5m /
≤60m) with deterministic integrity checks and a checksummed report. Redis loss never destroys durable
state (durable jobs stay in PostgreSQL; signed ingestion fails closed without replay). Regional
failover is a declared-incident, separation-of-duties, audited procedure (`docs/RegionalFailover.md`);
failback is manual (`docs/RegionalFailback.md`). Runbooks: `docs/runbooks/`. Certify with a staging
restore drill + regional rehearsal (`docs/RestoreDrills.md`). CI runs the reliability fencing,
restore-verify, and failover tests plus a scripts + docs check — no real cloud infrastructure is
contacted.
