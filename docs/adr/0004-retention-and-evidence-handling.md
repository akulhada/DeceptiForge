# ADR 0004 — Retention and evidence-at-rest handling

**Status:** Accepted

## Context

Alerts, monitoring events, and incidents carry evidence-bearing JSON that can include sensitive
context. The platform must bound how long raw data is kept, encrypt it at rest, and keep retention
safe under multi-worker/multi-region operation — without losing legally-held or audit records.

## Decision

- Evidence-bearing JSON (alerts/events/incidents) is **encrypted at rest**
  (`EVIDENCE_ENCRYPTION_MODE`, key via `EVIDENCE_ENCRYPTION_KEY`); a non-disabled mode is required by
  production startup validation.
- Retention and lifecycle cleanup run as **scheduled, advisory-locked, org-scoped, batched** jobs
  (`app/jobs/retention.py`, `app/jobs/incident_lifecycle.py`), not inline on the request path.
- Raw activity events expire **before** the derived violations/session summaries that reference them;
  cleanup is auditable.
- Only the primary region runs schedulers/side-effect workers; retention skips on a non-leader region
  (see [ADR 0005](0005-release-certification-criteria.md) and the reliability docs).
- Audit records survive retention, backup, and restore. **Legal holds are not implemented**: there
  is no hold model and no retention or deletion path consults one, so nothing is exempted from
  retention today. Implementing them requires an organization-scoped hold model enforced in every
  deletion path plus a restore-drill check; until then no document, drill, or UI may claim holds.

## Consequences

- Durable authoritative state lives in PostgreSQL; Redis loss never destroys it and signed ingestion
  fails closed without the replay store.
- A restore is not trusted until a drill verifies encrypted fields still decrypt and legal-hold/audit
  records remain intact.
- Changing retention windows, encryption mode, or the leader-only execution model is a boundary change
  and should reference this ADR.
