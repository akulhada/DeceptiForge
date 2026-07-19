# Staging deployment scripts

Run in this order. All scripts print only presence/validity — never secret values. Source your
staging environment (rendered by the secret manager from `.env.staging.example`) before running.

| Step | Script | Purpose |
| --- | --- | --- |
| 1 | `preflight.sh` | Validate config is safe; render prod Compose; run `Settings.validate_runtime()`. Exits non-zero on any unsafe setting. |
| 2 | `migrate.sh` | Apply migrations as a **separate** step (never from API startup). Back up the DB first. |
| 3 | *(deploy)* | Bring up the prod-shaped topology (API + Postgres + Redis + reconstruction worker + lifecycle/retention worker). API does not run migrations. |
| 4 | `verify_runtime.sh` | 19-point runtime safety verification (health/readiness, UID 10001, demo-404, signed-ingestion controls, cross-org, CORS, request_id, workers running). |
| 5 | `smoke_test.sh` | End-to-end signed ingestion + replay/tamper/expired rejection (invoked by step 4 when its env is present). |
| — | `rollback.sh` | Controlled image-only rollback (never touches the database). |

## Multi-worker (distributed control) verification

Run **two or more** API replicas sharing one Redis (the prod Compose sets `deploy.replicas: 2`).
The distributed guarantees are proven in CI (`redis-integration` and `postgres-integration` jobs);
on staging, confirm them against the live cluster:

1. Rate limit is shared: send more than `MONITORING_RATE_LIMIT_PER_MINUTE` signed requests across
   both replicas within a minute; the budget is enforced in aggregate (429 once exceeded), not
   per-replica.
2. Replay is shared: capture one signed request; submit it to replica A (accepted), then submit the
   **same nonce** to replica B — it is rejected (409). `smoke_test.sh` proves single-node replay;
   for cross-node, target each replica's address directly (bypass the load balancer).
3. Concurrent duplicates: fire 20–100 concurrent identical signed events at the same episode; verify
   exactly **one** alert, correct `event_count`, earliest `first_seen`, latest `last_seen`, no
   duplicate incident, and no database integrity error returned to the client.

## Retention / lifecycle verification (synthetic data only)

Use synthetic staging data. Do not run against real customer data.

1. Confirm the retention and incident-lifecycle services are running (step 4 checks this).
2. Seed synthetic, aged monitoring events / stale incidents for **two** organizations.
3. Run `python -m app.jobs.retention` and `python -m app.jobs.incident_lifecycle` (or wait for the
   scheduled cron). Confirm from the structured logs (counts only, no evidence):
   - expired monitoring events deleted per policy;
   - stale incidents marked; resolved/stale incidents archived past the window;
   - narrative revisions pruned to the retention count;
   - one organization's cleanup does not affect the other (organization-safe);
   - concurrent runs are safe (advisory lock; bounded batches).

Record every outcome in `docs/checklists/StagingVerification.md`.
