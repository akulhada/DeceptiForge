<!-- Purpose: document the minimal production boundary (auth stub, org scoping, narrative
revisions, cooldown). Responsibilities: describe what is enforced and what remains. Future
modules: replace the stub with real identity and tenant provisioning. -->

# Production Boundary

A minimal, credible boundary for the API and narrative system. It is **not** user management,
OAuth, or RBAC — it is an API-key/organization-id stub plus organization-scoped lookups.

## Auth stub

`require_org` resolves the requesting organization:

- `AUTH_ENABLED=false` (development/demo only) → bypass to the demo organization, so the local
  dashboard works without headers.
- `AUTH_ENABLED=true` → require an API key from `API_KEY_BINDINGS` (JSON map of key to organization
  UUID). The key determines the organization; a mismatching `X-DeceptiForge-Org-Id` is rejected.
  Missing/invalid key → `401`; mismatching organization → `403`.

This is a placeholder, not production-grade identity. There are no accounts, sessions, or roles.

## Organization scoping

**Every** persisted artifact carries an `organization_id`: repositories, context profiles,
placement plans, decoy plans, validation reports, detection events, alerts, incidents, and
narrative revisions. Every read filters by `organization_id` and every write stamps it — no read or
write path is globally scoped by default.

Propagation: `require_org` resolves the organization, the HTTP layer builds
`PipelineService(repository, organization_id)`, and the service passes that id to every repository
call. Services never silently default to global state; the demo path explicitly uses the demo
organization (a single tenant), documented in `DemoService`.

Effects:

- Reading another organization's repository profile / plan / decoy / validation / monitor / alert /
  incident returns `404`, or `409` for a use case whose prerequisite belongs to another org.
- **Incident reconstruction is organization-scoped.** `ingest_event` reconstructs only from
  `alerts_for_organization(org)` and calls `replace_incidents_for_organization(org, …)`, which
  deletes and rebuilds **only that organization's** incidents. Other tenants' incidents are never
  deleted or modified.
- Narrative revisions are unique per `(organization_id, incident_id, revision_number)`, enforced by
  a database unique constraint (`uq_narrative_revision_scope`, migration `0004`).

## Narrative revisions

Each generation appends an immutable revision (`narrative_revisions`), never overwriting. A
revision stores organization id, incident id, `revision_number`, `context_hash`, source status,
model, prompt version, timestamps, token usage, and the narrative content.

- `GET /incidents/{id}/narrative` → latest revision (org-scoped).
- `GET /incidents/{id}/narratives` → all revisions (org-scoped).
- `POST /incidents/{id}/narrative[?force=true]` → generate or reuse.

## Cooldown / reuse (cost control)

`POST` avoids needless model spend:

- if a prior revision has the **same `context_hash`** and it was a **model success**, it is reused;
- if the prior revision was a fallback, it is reused while within `NARRATIVE_COOLDOWN_SECONDS`;
- `force=true` always regenerates (new revision).

## Deterministic data stays authoritative

GPT prose is untrusted **presentation text**. It never sets or edits severity, confidence,
evidence, alerts, or incidents. The incident panel shows deterministic reconstruction as the
source of truth; the AI summary is clearly labeled and optional. A test asserts incident data is
unchanged after narrative generation.

## Token budget note

The token budget guard is a **heuristic** (~4 characters per token) with a conservative default.
It is intentionally simple for the MVP: it drops low-priority timeline detail first, then reduces
evidence excerpts, always preserving severity/type/recommendations/caveats, and records truncation
metadata. It is not a tokenizer-accurate measurement.

## Run locally

`apps/api/.env` (from `.env.example`) sets `AUTH_ENABLED=false` and `DEMO_ENABLED=true`, so the
demo runs without headers. To exercise the boundary locally, set `AUTH_ENABLED=true` and send:

```sh
curl -sX POST localhost:8000/incidents/<id>/narrative \
  -H 'X-DeceptiForge-API-Key: local-development-key' \
  -H 'X-DeceptiForge-Org-Id: 00000000-0000-0000-0000-0000000000de'
```

## Demo route gating

Demo routes (`/demo/*`) mount **only when `DEMO_ENABLED=true` AND `APP_ENV=development`**. They can
never be exposed on a production-like deployment, even if `DEMO_ENABLED` is set to true. Auth-bypass
(`AUTH_ENABLED=false`) is likewise restricted to development; in a production environment a disabled
auth flag is rejected with `401` rather than silently bypassed.

## Stabilization sprint (fixed)

- Alert deduplication and event counting now persist across requests (the alerting pipeline is
  seeded from stored alerts; the deterministic alert id merges the same row).
- Incident reconstruction groups on strong keys only (trace/decoy/placement/correlation) — unrelated
  traces sharing a monitor are never merged — and is bounded to recent alerts.
- Incident writes upsert only the affected organization's incidents (no global delete/reinsert).
- Monitoring values, request bodies, and serialized artifacts have size limits (413); monitoring and
  narrative have per-organization in-process rate limits.
- API keys bind to exactly one organization; a shared key can no longer act as an arbitrary org.
- Global exception handlers return safe, `x-request-id`-correlated responses; CORS fails closed and
  refuses wildcard-with-credentials; the container runs non-root without auto-migrations.

See [Deployment](Deployment.md) for env, migrations, and container guidance.

## Remaining work (production hardening)

- Real identity/OAuth/RBAC and key rotation; replace the API-key-to-org binding stub.
- Repository integrations (GitHub/GitLab app installs, repository ids) instead of local-path
  scanning, which stays development-only.
- Durable/async monitor ingestion and deduplication (current ingest is synchronous per request).
- **Distributed** rate limiting (the current limiter is single-process only) and edge/reverse-proxy
  body/connection limits.
- Scheduled retention/cleanup (only narrative-revision pruning is implemented; event retention is a
  documented target).
- Tokenizer-accurate budgeting; production monitoring/log aggregation; dependency lockfile; CI/CD.
