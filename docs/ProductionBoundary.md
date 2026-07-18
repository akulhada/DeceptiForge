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
- `AUTH_ENABLED=true` → require `X-DeceptiForge-API-Key` (equal to `DEMO_API_KEY`) and a valid
  `X-DeceptiForge-Org-Id`. Missing/invalid key → `401`; missing/invalid org id → `400`.

This is a placeholder, not production-grade identity. There are no accounts, sessions, or roles.

## Organization scoping

`repositories`, `alerts`, `incidents`, and `narrative_revisions` carry an `organization_id`. Demo
and pipeline writes stamp the demo organization by column default (no engine changes).

Incident and narrative reads are **organization-scoped**: they fetch by `(organization_id,
incident_id)`, never by id alone. A narrative request for an incident in another organization
returns `404`. Narrative generation verifies incident ownership before doing any work.

Scoping other pipeline artifacts (decoy plans, validation reports, monitor events, context/
placement) is deliberately deferred; they are not reachable cross-tenant through the narrative
surface. See "Remaining work".

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

## Remaining work (production hardening)

- Real identity/tenant provisioning; replace the demo-org default and API-key stub.
- Organization-scope the remaining pipeline artifacts (decoy plans, validation reports, monitor
  events, context, and placement) before exposing them to multiple tenants.
- Rate limiting beyond the per-incident reuse/cooldown.
- Tokenizer-accurate budgeting if prompts grow.
