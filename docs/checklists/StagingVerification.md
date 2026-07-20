<!-- Purpose: capture evidence for one controlled-staging deployment + runtime verification of
DeceptiForge. Fill during/after the run — DO NOT prefill results that were not observed. -->

# Staging verification record

One record per staging deployment. Copy this file per run. Attach real evidence (CI URL, script
output). A result is only "pass" if it was actually observed.

## Deployment identity

| Field | Value |
| --- | --- |
| Deployment date | |
| Commit SHA | |
| Release tag | e.g. `v0.1.0-rc1` |
| Deployed by | |
| Approver | |

## Release gate — remote CI (attach the run URL; do not claim green without it)

| Job | Result (pass/fail) | Notes |
| --- | --- | --- |
| CI run URL | | |
| backend-quality | | |
| postgres-integration (live migrations) | | |
| postgres-integration (concurrent ingestion) | | |
| redis-integration (replay + rate limit) | | |
| frontend | | |
| production-config (settings smoke + Compose) | | |
| docker (build + UID 10001 + health/readiness) | | |
| secret-scan (pinned Gitleaks) | | |

## Deploy + runtime verification (from the staging scripts)

| # | Check | Result | Evidence |
| --- | --- | --- | --- |
| — | `preflight.sh` PASS | | |
| — | `migrate.sh` OK (separate from API) | | |
| — | Compose/topology renders | | |
| 1 | API runs as UID 10001 | | |
| 2 | Health endpoint 200 | | |
| 3 | Readiness endpoint responds | | |
| 4 | PostgreSQL healthy | | |
| 5 | Redis healthy | | |
| 6 | `/demo/*` returns 404 | | |
| 7 | Local filesystem scan rejected (403) | | |
| 8 | Unsigned monitoring rejected (401) | | |
| 9 | Invalid signature rejected (401) | | |
| 10 | Expired timestamp rejected (400) | | |
| 11 | Reused nonce rejected (409) | | |
| 12 | Invalid API key rejected (401) | | |
| 13 | Cross-organization access rejected (403) | | |
| 14 | CORS allows only configured origins | | |
| 15 | Safe errors include request_id | | |
| 16 | Logs contain no secrets/signatures/keys/payloads/evidence | | |
| 17 | API startup did NOT run migrations | | |
| 18 | Reconstruction worker running | | |
| 19 | Retention/lifecycle worker running | | |

## Signed ingestion (end to end)

| Check | Result | Evidence |
| --- | --- | --- |
| Signed event accepted | | |
| Alert created | | |
| Reconstruction job queued/processed | | |
| Incident appears | | |
| Narrative generated (if enabled) | | |
| Replay of same request rejected | | |
| Body tamper (reused signature) rejected | | |
| Expired timestamp rejected | | |

## Multi-worker (≥2 replicas, shared Redis)

| Check | Result | Evidence |
| --- | --- | --- |
| Rate limit shared across workers | | |
| Nonce accepted by A rejected by B | | |
| Concurrent duplicates → one alert | | |
| event_count correct | | |
| first_seen earliest / last_seen latest | | |
| No duplicate incidents | | |
| No DB integrity error exposed to clients | | |

## Retention / lifecycle (synthetic data only)

| Check | Result | Evidence |
| --- | --- | --- |
| Retention worker executes (bounded batches) | | |
| Incident lifecycle worker executes | | |
| Advisory/distributed lock works | | |
| Expired events deleted/archived per policy | | |
| Stale incidents marked per policy | | |
| Narrative revision retention enforced | | |
| One org's cleanup does not affect another | | |
| Logs report counts without evidence | | |

## Observability

| Signal present (no secrets) | Result |
| --- | --- |
| request_id | |
| auth failures / authz failures | |
| signature verification failures | |
| nonce replay rejection | |
| rate-limit rejection | |
| ingestion + alert-upsert latency | |
| reconstruction queue/job status | |
| retention + lifecycle counts | |
| dependency health | |

## Decision

| Field | Value |
| --- | --- |
| Known limitations | |
| Go / No-Go | |
| Rationale | |

**Status after this record:** `Controlled staging verified` **or** `Staging no-go with documented
failures`. This milestone does NOT constitute full production certification: no enterprise SSO/RBAC,
no real provider integrations, and live decoy deployment to GitHub is a fake adapter only. The
browser/RAG/MCP/database/agent sensors, measured coverage engine, SIEM export, and multi-region
reliability ARE implemented (each disabled by default behind its own feature flag) — enabling any of
them in staging requires exercising its verification steps in this record, not treating it as absent.
