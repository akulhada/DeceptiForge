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
