<!-- Purpose: manual incident/alert export formats and scope. -->

# Incident export

Analysts can export a single incident or alert (organization + permission scoped:
`incidents:export`, `alerts:export`). Rendering (`app/services/integrations/export.py`) operates on
an already-minimized canonical envelope — no raw evidence or secrets.

## Formats

- **JSON** — the canonical envelope(s).
- **JSON Lines** — one envelope per line.
- **CSV** — a bounded summary (event id, type, severity, time, title, source, surfaces).
- **Markdown** — a human-readable incident report; any AI narrative is labeled non-authoritative.
- **STIX 2.1** — a minimal, conservative bundle (see below).

`GET /security-export/incidents/{id}?format=json|jsonl|csv|markdown|stix`;
`GET /security-export/alerts/{id}?format=...`.

## STIX mapping (conservative)

The bundle records a `note` per event carrying the deterministic summary, plus a versioned custom
`x_deceptiforge_extension` (`df-stix-v1`). Synthetic decoy markers are **never** emitted as malicious
`indicator` objects — they are recorded as notes/observed-data only, and the extension flags
`synthetic_decoy: true`. Fields that do not semantically fit STIX are not forced.

## Limitations

Date-range and multi-object bundles are built by rendering multiple envelopes; the first release
exports one incident/alert per request.
