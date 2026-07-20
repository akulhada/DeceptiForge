<!-- Purpose: document the SIEM/SOAR export framework — canonical event, payload profiles, data
minimization, credential handling, outbox delivery, retry/dead-letter, and SSRF controls. -->

# Security integrations (SIEM / SOAR export)

DeceptiForge delivers **minimized, signed** alerts, incidents, coverage events, and operational
signals to enterprise security platforms. Delivery is asynchronous — it never runs in the ingestion
path — and no export is lost after a committed alert/incident.

Disabled by default (`SECURITY_INTEGRATIONS_ENABLED`); explicit staging/production enablement
required. Explicit opt-in per integration; organization-scoped.

## Supported destinations

Generic signed webhook, Splunk HTTP Event Collector, Microsoft Sentinel (transport-agnostic
ingestion), and Elastic. All isolated behind one `SecurityExportAdapter` contract
(`app/services/integrations/adapters.py`). See
[Splunk](integrations/Splunk.md), [Sentinel](integrations/Sentinel.md), [Elastic](integrations/Elastic.md).

## Canonical event

Every destination receives a versioned `SecurityEventEnvelope` (`schema_version`
`df-security-event-v1`). Deterministic fields are authoritative; the optional GPT narrative is
labeled non-authoritative (`metadata.narrative_label`) and only included when the integration allows
it. The envelope carries ids, severity, bounded title/summary, trace ids, decoy types, affected
surfaces, recommended actions, and a deterministic evidence summary — **never** raw evidence,
prompts, rows, pasted text, agent streams, secrets, or stack traces.

Event types: `deceptiforge.alert.*`, `deceptiforge.incident.*`, `deceptiforge.coverage.*`,
`deceptiforge.monitor.*` / `.connector.*` / `.retention.*` / `.reconstruction.*` /
`.integration.*` operational events.

## Payload profiles

`minimal` (ids + severity + title + timestamp + event type + trace/org reference), `standard`
(+ summary, surfaces, decoy type, confidence, recommended actions, links), `analyst` (+ deterministic
evidence summary + optional labeled narrative), `compliance_summary` (deterministic-only). Raw
evidence is never included by any profile; the hard size bound
(`SECURITY_EXPORT_MAX_PAYLOAD_BYTES`) is enforced.

## Transactional outbox + delivery

`emit_event` (`outbox.py`) creates one idempotent delivery row per matching active integration **in
the same DB transaction** as the source commit. The delivery worker
(`python -m app.jobs.security_export`) claims due rows with a lease (two workers never deliver the
same row), revalidates the endpoint for SSRF, builds the destination request, sends it via the
production HTTP transport (redirects disabled), and records success / retry / dead-letter.

## Retry and dead-letter

Retryable: connection/DNS/timeout, 408, 429, 5xx. Permanent (no retry): invalid credentials,
forbidden, malformed payload, other 4xx. Exponential backoff with bounded jitter and `Retry-After`
support; after `SECURITY_EXPORT_MAX_ATTEMPTS` or `SECURITY_EXPORT_MAX_AGE_HOURS` a delivery is
dead-lettered (hash + metadata retained, longer than the full payload). Analysts can manually retry.

## Idempotency

The idempotency key is `org:integration:event_type:source_id:vN`. One logical event yields one
delivery per integration; retries never duplicate; an event **update** bumps the version and
produces a new delivery rather than a silent overwrite. Elastic uses the delivery id as the document
id so a duplicate is an idempotent overwrite.

## Credentials + SSRF

Integration credentials are encrypted at rest and decrypted only inside the delivery worker; they are
never returned by the API or written to logs. Endpoints are SSRF-validated at create and again before
every delivery — see [WebhookVerification](WebhookVerification.md). Data-residency policy controls
allowed domains, private-network policy, and whether the narrative/trace/user identifiers may leave
the platform; export fails closed when policy blocks it.

## Manual export

Analysts can export an incident or alert as JSON, JSON Lines, CSV, Markdown, or a minimal STIX 2.1
bundle — see [IncidentExport](IncidentExport.md).
