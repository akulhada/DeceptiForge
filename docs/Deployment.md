<!-- Purpose: document production-oriented deployment of the API. Responsibilities: migrations,
required env, container behavior, limits, and remaining gaps. Future modules: expand as real
identity, distributed limiting, and async ingestion land. -->

# Deployment (controlled staging)

This is a hardened MVP, safe for controlled staging — **not** full production SaaS. Real identity,
RBAC, key rotation, distributed rate limiting, async ingestion, and log aggregation remain future
work.

## Migrations (separate release step)

The API container does **not** run migrations automatically. Run them as a one-off before rollout:

```sh
docker run --rm -e DATABASE_URL=... <image> alembic upgrade head
# or, on a release host:
cd apps/api && alembic upgrade head
```

## Container behavior

- Runs as a non-root user (`appuser`, uid 10001).
- Default command serves only (`uvicorn app.main:app`); no migrations at startup.
- `HEALTHCHECK` probes `/docs` via the standard library.
- No secrets are baked into the image; all secrets come from the environment at runtime.
- Dependencies install from `pyproject` ranges (no lockfile yet — FUTURE_HARDENING: pin via a
  lockfile / hashes).

## Required environment (production-like)

| Variable | Purpose |
| --- | --- |
| `APP_ENV` | `production` disables demo routes, local scanning, and auth bypass |
| `DATABASE_URL` | PostgreSQL DSN |
| `AUTH_ENABLED` | `true` in production (bypass rejected outside development) |
| `API_KEY_BINDINGS` | JSON map of API key → single organization UUID |
| `CORS_ORIGINS` | explicit allow-list; empty = CORS off (fail closed) |
| `CORS_ALLOW_CREDENTIALS` | `true` only with non-wildcard origins |
| `DEMO_ENABLED` | must be `false` in production (demo also needs `APP_ENV=development`) |
| `OPENAI_API_KEY` | optional; absent → deterministic narrative fallback |

## API key / organization binding

Each API key maps to exactly one organization via `API_KEY_BINDINGS`. A request whose
`X-DeceptiForge-Org-Id` does not match the key's bound organization is rejected (`403`). One shared
key can no longer act as an arbitrary organization. The demo key shortcut works **only** in
development.

## Limits (single-process MVP)

- Request body limit: `MAX_REQUEST_BODY_BYTES` (413 on exceed).
- Monitoring value limit: `MONITORING_MAX_VALUE_BYTES` (413; not persisted).
- Artifact size limit: `MAX_ARTIFACT_BYTES` (413 before persistence).
- Rate limits (in-process): `MONITORING_RATE_LIMIT_PER_MINUTE`, `NARRATIVE_RATE_LIMIT_PER_MINUTE`.
  **This limiter is per-process and does not coordinate across workers/hosts** — production needs an
  edge/distributed limiter and a reverse proxy that enforces body/connection limits.
- Retention: `NARRATIVE_REVISION_RETENTION_COUNT` (pruned), `MONITORING_EVENT_RETENTION_DAYS`
  (documented target; scheduled cleanup is future work).

## Errors and correlation

Every response carries `x-request-id`. Unexpected errors return a safe body
(`{"detail":"internal server error","request_id":...}`) with no stack trace, filesystem path, SQL,
provider detail, or raw payload. Structured error metadata is logged server-side.

## Remaining production hardening

Real identity/OAuth/RBAC and key rotation; distributed rate limiting; async/durable monitor
ingestion and deduplication; repository integrations (no local-path scanning); scheduled retention;
production monitoring and log aggregation; dependency lockfile.
