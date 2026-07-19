<!-- Purpose: gate a controlled staging deployment of DeceptiForge. Responsibilities: enumerate the
checks that must hold before rollout. Cross-references: docs/Deployment.md, docs/monitor-signing.md,
docs/bootstrap-and-encryption.md. -->

# Staging release checklist

Complete every item before deploying to controlled staging. Boxes map to CI gates where possible;
items marked **manual** are operator responsibilities not enforceable in CI.

## CI and code

- [ ] CI is green on the release commit: `backend-quality`, `postgres-integration`,
      `redis-integration`, `frontend`, `production-config`, `docker`, `secret-scan`.
- [ ] `production-config` proves the exact production-like `Settings.validate_runtime()` passes and
      every unsafe deviation fails.
- [ ] `production-config` renders `docker-compose.prod.example.yml`; the file explicitly sets
      `MONITOR_SIGNATURE_REQUIRED: 'true'`, `APP_ENV: production`, `DEMO_ENABLED: 'false'`.
- [ ] `postgres-integration` applied migrations up → down → up on live PostgreSQL and confirmed the
      `uq_alert_episode` constraint and key tables exist.
- [ ] `postgres-integration` proved concurrent duplicate ingestion yields one alert with the correct
      `event_count`.
- [ ] `docker` verified UID **10001**, no migration-on-start, `/health`, `/ready`, and demo 404.
- [ ] `secret-scan` (Gitleaks, pinned + checksum-verified) is clean.

## Data and migrations

- [ ] **manual** Database backup taken and a tested rollback plan exists (migrations are a separate
      release step: run `alembic upgrade head` before rollout; keep the previous revision to
      `alembic downgrade` to if needed).
- [ ] **manual** Migration release job run against staging PostgreSQL (not by the API container).

## Secrets and configuration

- [ ] **manual** All secrets (DB password, `EVIDENCE_ENCRYPTION_KEY`, monitor signing secrets)
      loaded from the secret manager — never from committed files.
- [ ] `MONITOR_SIGNATURE_REQUIRED=true`; signed monitor credentials provisioned and distributed to
      collectors (see `docs/monitor-signing.md`).
- [ ] `BOOTSTRAP_KEYS_ENABLED=false` and `API_KEY_BINDINGS` removed after the first DB-backed owner
      key was minted (see `docs/bootstrap-and-encryption.md`).
- [ ] `EVIDENCE_ENCRYPTION_MODE=local` (or a documented KMS strategy) with a real key.
- [ ] `RATE_LIMIT_BACKEND=redis` (or `RATE_LIMIT_MODE=gateway`) and `REPLAY_BACKEND=redis`.
- [ ] `CORS_ORIGINS` set to the explicit dashboard origin(s); no wildcard.

## Network and ingress

- [ ] **manual** PostgreSQL and Redis are private (no published host ports).
- [ ] **manual** TLS terminated at ingress; API not exposed directly.
- [ ] **manual** Ingress body-size limit configured (≈1 MiB) as defense in depth alongside the app's
      streaming limit.

## Runtime and workers

- [ ] **manual** Two or more API replicas (rate limits and replay nonces shared via Redis).
- [ ] **manual** Reconstruction worker running (`python -m app.jobs.reconstruction`).
- [ ] **manual** Retention and incident-lifecycle jobs scheduled (`python -m app.jobs.retention`,
      `python -m app.jobs.incident_lifecycle`).
- [ ] **manual** Structured logs/metrics shipped to the aggregator; confirm no secrets, signatures,
      nonces, or decrypted evidence appear.

## Smoke verification (post-deploy)

- [ ] **manual** `/health` returns ok; `/ready` reports database and Redis healthy.
- [ ] **manual** A signed monitoring ingest succeeds; an unsigned one is rejected (401).
- [ ] **manual** A replayed nonce is rejected (409); an oversized body is rejected (413).
- [ ] **manual** Alerts and incidents appear after the reconstruction worker runs.
- [ ] **manual** The production dashboard loads via tenant endpoints and never calls `/demo/*`.

## Data handling

- [ ] **manual** No real sensitive customer data in staging without an approved encryption setup.
