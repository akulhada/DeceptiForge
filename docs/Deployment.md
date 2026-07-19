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
```

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

## Errors and correlation

Every response carries `x-request-id`. Unexpected errors return a safe body
(`{"detail":"internal server error","request_id":...}`) with no stack trace, path, SQL, provider
detail, or raw payload. Structured metrics/logs never include secrets, signatures, raw bodies, or
decrypted evidence.
