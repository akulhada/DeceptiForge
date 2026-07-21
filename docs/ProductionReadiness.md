<!-- Purpose: honest production-readiness status after the master stabilization milestone. -->

# Production readiness

**Recommendation: controlled staging with a trusted reverse proxy and Redis/edge rate limiting —
not open multi-tenant production.** The system is materially safer than the hackathon MVP but is not
a finished SaaS.

## Now in place

- Opt-in tenant capacity management: Redis-backed monitoring burst/sustained quotas, pending
  reconstruction queue backpressure, tenant-scoped usage/limit APIs, fair reconstruction claims, and
  capacity recommendations that remain `uncertified` until a measured staging run exists.

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

- Rate limiter and replay nonce store are Redis-backed for multi-worker/production
  (`RATE_LIMIT_MODE=app` + `RATE_LIMIT_BACKEND=redis`, `REPLAY_BACKEND=redis`); a single-worker
  staging deployment may use in-process, and the config guard enforces Redis outside development.
- `API_KEY_BINDINGS` env keys remain a time-boxed bootstrap path (must set `BOOTSTRAP_EXPIRES_AT`).
- Monitor ingestion is signed (`monitor-signature-v1` HMAC over the request body) with a separate
  encrypted monitor-credential model and distributed replay protection.
- Evidence-bearing JSON blobs (alerts/events/incidents) are encrypted at rest; retention/lifecycle
  cleanup runs as scheduled advisory-locked jobs (`app/jobs/retention.py`, `incident_lifecycle.py`).
- No real identity/OAuth/SSO/RBAC beyond role→scope, and no key rotation.
- Repository scanning stays local/development-only; live GitHub App deployment is a fake adapter
  only — provider integrations remain future work.
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

## Dashboard security headers

The dashboard holds a tenant API key in `sessionStorage`, so a single injected script is enough to
exfiltrate a working credential. Next.js therefore emits, on every document response:

| Header | Value | Purpose |
| --- | --- | --- |
| `Content-Security-Policy` | per-request nonce + `strict-dynamic` | no `'unsafe-inline'`/`'unsafe-eval'` for scripts; `connect-src` limited to `self` and `NEXT_PUBLIC_API_URL`, so a stolen key cannot be posted elsewhere |
| `X-Frame-Options` | `DENY` | clickjacking (with `frame-ancestors 'none'` in the CSP for modern agents) |
| `X-Content-Type-Options` | `nosniff` | MIME confusion |
| `Referrer-Policy` | `strict-origin-when-cross-origin` | keeps paths and query out of cross-origin referrers |
| `Permissions-Policy` | camera/microphone/geolocation/payment/USB denied | powerful features are never needed here |
| `Strict-Transport-Security` | `max-age=31536000; includeSubDomains` | honoured only over HTTPS |

`style-src` deliberately retains `'unsafe-inline'`: Next injects inline style attributes with no
nonce channel. Style injection is materially less dangerous than script execution, and `script-src`
is the control that protects the session key.

CI boots the production build and asserts these headers on real HTTP responses, including that
`script-src` contains no `'unsafe-inline'` and that the CSP carries a nonce. `apps/web/services/
securityHeaders.test.ts` locks the policy contract itself.

### Deployment requirement (not proven by CI)

**CI proves only that the application emits these headers.** It does not prove that a deployed edge
preserves them, because no ingress, reverse proxy, or CDN configuration ships in this repository —
`docker-compose.prod.example.yml` publishes no web service, and ingress terminates in front of the
API by assumption. Before any internet-facing deployment the operator must:

1. Confirm the ingress or CDN forwards `Content-Security-Policy` unchanged rather than stripping,
   caching, or rewriting it — a cached CSP would pin one nonce across users and break the page.
2. Ensure the CSP response is not cached by a shared cache, or that the edge revalidates per request.
3. Re-add any header the edge strips, and set `Strict-Transport-Security` at the TLS terminator if it
   is not the Next.js process.
4. Set `NEXT_PUBLIC_API_URL` to the real API origin at **build** time; `connect-src` is baked from it,
   and a wrong value blocks every API call.
5. Re-run the same header assertions against the deployed hostname, not against localhost.

Until step 5 is evidenced against a real environment, treat ingress header preservation as unverified.
