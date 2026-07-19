<!-- Purpose: document deployment of the API for single-worker staging and multi-worker production.
Responsibilities: migrations, required env, distributed dependencies, lifecycle workers, limits,
ingress, and container behavior. -->

# Deployment

Two supported shapes:

- **Single-worker staging** — one API process. In-memory rate limiting and replay are acceptable
  (`RATE_LIMIT_BACKEND=memory`, `REPLAY_BACKEND=memory`), no Redis required.
- **Multi-worker production** — two or more replicas. Rate limiting and replay **must** be
  Redis-backed so limits and nonces are shared across workers. See `docker-compose.prod.example.yml`.

## Migrations (separate release step)

The API container never runs migrations at startup. Run them as a one-off before rollout:

```sh
docker run --rm -e DATABASE_URL=... <image> alembic upgrade head
# or, from a release host with the staging environment sourced:
scripts/staging/migrate.sh
```

## Controlled staging: scripts and procedure

See `scripts/staging/README.md`. Order: `preflight.sh` → `migrate.sh` → deploy the prod-shaped
topology → `verify_runtime.sh` (+ `smoke_test.sh`). `rollback.sh` performs an image-only rollback
and never touches the database. Record evidence in `docs/checklists/StagingVerification.md`; gate the
go/no-go with `docs/checklists/StagingRelease.md`. Configure the environment from
`.env.staging.example` (placeholders only; render real secrets from your secret manager).

## Release-candidate tagging

Tag the exact commit only after the remote CI run for that commit is green (all jobs). Do not tag a
commit whose CI is red or unverified.

```sh
git switch main
git pull origin main
git status                 # must be clean
# Confirm the remote CI run for this commit is green (attach the URL to the verification record).
git tag -a v0.1.0-rc1 -m "DeceptiForge controlled staging candidate"
git push origin v0.1.0-rc1
```

If `v0.1.0-rc1` already exists, do not overwrite it — use the next number (`-rc2`, …).

## Lifecycle workers (separate from API replicas)

Cleanup and reconstruction do not run implicitly in API replicas. Deploy these as separate
worker/cron services (see the prod compose example):

| Command | Role |
| --- | --- |
| `python -m app.jobs.reconstruction` | drains the incident-reconstruction queue off the hot path |
| `python -m app.jobs.retention` | purges aged events/alerts/jobs/keys, prunes narrative revisions |
| `python -m app.jobs.incident_lifecycle` | retires stale incidents, archives resolved/stale ones |

Jobs are idempotent, batched, organization-safe, and guarded by a PostgreSQL advisory lock, so
concurrent runs are safe.

## Required environment (multi-worker production)

| Variable | Purpose |
| --- | --- |
| `APP_ENV=production` | disables demo routes, local scanning, and auth bypass |
| `DATABASE_URL` | PostgreSQL DSN (private network) |
| `AUTH_ENABLED=true` | bypass rejected outside development |
| `REDIS_URL` | required when a Redis-backed backend is selected (private network) |
| `RATE_LIMIT_MODE` | `app` (with `RATE_LIMIT_BACKEND=redis`) or `gateway` (edge enforces) |
| `RATE_LIMIT_BACKEND=redis` | required in `app` mode; production refuses in-memory |
| `REPLAY_BACKEND=redis` | required in production; production refuses in-memory |
| `REDIS_FAIL_MODE` | `closed` (reject on outage, default) or `open` (degrade to allow) |
| `MONITOR_SIGNATURE_REQUIRED=true` | require HMAC-signed ingestion (see `monitor-signing.md`) |
| `EVIDENCE_ENCRYPTION_MODE` | `local` (with `EVIDENCE_ENCRYPTION_KEY`) or a documented KMS strategy |
| `BOOTSTRAP_KEYS_ENABLED` | `false` in steady state (see `bootstrap-and-encryption.md`) |
| `CORS_ORIGINS` | explicit allow-list; empty = CORS off (fail closed) |

Production **fails fast at startup** on: in-memory rate-limit/replay backends, missing `REDIS_URL`
when required, an unreachable required Redis, `EVIDENCE_ENCRYPTION_MODE=disabled`, or unrestricted
(no-expiry) bootstrap keys.

## Health / readiness

- Liveness: `GET /health` (also the container `HEALTHCHECK`).
- Readiness: `GET /ready` reports database and Redis dependency state; returns `503` if a required
  dependency is down. Neither endpoint discloses connection strings or secrets.

## Limits and ingress

- The app enforces a **streaming** request-body limit (`MAX_REQUEST_BODY_BYTES`): oversized
  Content-Length **and** chunked/no-length bodies are rejected with `413` without buffering.
- Also configure an ingress body-size limit as defense in depth:
  - nginx: `client_max_body_size 1m;`
  - Traefik: `entryPoints.web.transport.maxRequestBodyBytes`
  - Envoy / cloud gateways: request size limit = 1 MiB.
- Per-value monitoring limit: `MONITORING_MAX_VALUE_BYTES` (413, not persisted).

## Container behavior

- Runs as non-root (`appuser`, uid 10001); CI asserts this.
- Serves only by default (`uvicorn app.main:app`); migrations are a separate step.
- No secrets baked into the image; all secrets come from the environment at runtime.

## Networking

Keep PostgreSQL and Redis on a private, non-published network. Do not publish their host ports in
production. Only the API (behind the edge/ingress) is reachable externally.

## Supported runtimes (pinned in CI)

| Runtime | Version |
| --- | --- |
| Python | 3.12 |
| Node | 24 (repo supports ≥ 22.13) |
| pnpm | from `packageManager` in `package.json` (single source of truth) |
| PostgreSQL | 16 |
| Redis | 7 |

## CI validation and local limitations

Some checks require services that were not available locally; they are delegated to CI and must not
be reported as locally passed.

**Verified locally**: ruff, mypy (on Python 3.13/3.14), the full pytest suite (SQLite +
fakeredis, plus real-Redis integration against a local Redis), Alembic **offline SQL generation**
of both upgrade and downgrade chains (PostgreSQL dialect), and `docker compose config` validation.

Offline SQL generation proves the migration operations render for the PostgreSQL dialect and the
revision chain is linear; it does **not** prove they apply against a real database, that UUID
defaults execute, or that unique constraints/indexes behave at runtime.

**Delegated to CI** (`.github/workflows/ci.yml`):

- **Live PostgreSQL migrations** — CI runs an ephemeral PostgreSQL 16 service and executes
  `alembic upgrade head` → `alembic current` → `alembic downgrade -1` → `alembic upgrade head`, then
  asserts the key tables exist. Local validation used offline SQL generation only because no local
  PostgreSQL server was available.
- **Docker runtime** — CI builds the API image, asserts the container runs as **UID 10001**
  (non-root), asserts the default command is `uvicorn` (migrations are **not** auto-run), and probes
  `/health`. Docker was not run locally because the Docker daemon was unavailable.
- **Redis distributed controls** — CI runs a Redis 7 service; the `redis_integration` tests prove
  cross-instance rate-limit sharing and cross-instance nonce rejection.
- **Secret scanning** — gitleaks (pinned CLI) scans tracked files and history with a documented
  allowlist for test fixtures (`.gitleaks.toml`).

## Inspecting CI failures

Backend gates are split into named steps (Ruff, MyPy, Pytest, each migration step) so the failing
gate is obvious in the Actions log. A safe diagnostics step prints tool versions and PostgreSQL /
Redis reachability — never secrets, passwords, keys, signatures, or raw environment contents.

## Errors and correlation

Every response carries `x-request-id`. Unexpected errors return a safe body
(`{"detail":"internal server error","request_id":...}`) with no stack trace, path, SQL, provider
detail, or raw payload. Structured metrics/logs never include secrets, signatures, raw bodies, or
decrypted evidence.
