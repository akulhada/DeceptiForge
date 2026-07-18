<!-- Purpose: document the GPT Incident Story Builder. Responsibilities: explain scope, data
boundaries, fallback, prompt versioning, token policy, and how to run with/without OpenAI.
Future modules: update when the prompt version or model policy changes. -->

# GPT Incident Story Builder

An **optional** narrative layer over deterministic incident reconstruction. It turns a sanitized,
minimized incident context into a security-analyst-style summary answering: what happened, why it
matters, the likely path, supporting evidence, next actions, and what remains uncertain.

Deterministic reconstruction stays the source of truth. GPT never sets severity, scoring, alerting,
or any security decision — it only writes prose from already-computed facts.

## Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/incidents/{incident_id}/narrative` | Generate (or regenerate) and persist a narrative |
| GET | `/incidents/{incident_id}/narrative` | Return a previously generated narrative (404 if none) |

Response is an `IncidentNarrative`: ids, `source` (`model`/`fallback`), `status`, `model`,
`prompt_version`, `source_context_hash`, `created_at`, a `body` (executive/analyst summary, likely
sequence, evidence, next actions, caveats, confidence notes), optional `token_usage`, and `error`.

## What is sent to GPT

Only the minimized `IncidentNarrativeContext`. Monitoring evidence is represented by a redacted
trace-observed marker; raw observed excerpts are not sent to GPT or copied into fallback narratives:

- incident id, type, severity, confidence, first/last seen
- affected surfaces, involved decoy/placement **counts**, trace ids
- timeline **summaries** (short text + evidence excerpt ≤ 120 chars)
- evidence excerpts (≤ 120 chars) and digests
- deterministic root-cause hypothesis, recommended actions
- false-positive notes, uncertainty notes, correlation reasons

## What is never sent

- raw secret values, full files, full documents, full database exports, full pasted content
- any decoy payload; only bounded excerpts and hashes leave the boundary

The context is validated by a test that asserts full excerpts and payloads never appear.

## Fallback behavior

The feature always returns a narrative:

- **No `OPENAI_API_KEY`** → deterministic fallback (`status = fallback_disabled`).
- **OpenAI call fails** → fallback with error metadata (`fallback_error`).
- **Model output fails schema validation** → fallback (`fallback_invalid`).

The deterministic fallback is built from incident fields, so the demo works without OpenAI.

## Prompt versioning

The prompt is versioned (`incident-narrative-v1`) in `app/prompts/incident_narrative.py` and stored
on every narrative. The system prompt forbids inventing facts, requires cautious language, forbids
"breach confirmed" unless the context says so, and forbids destructive remediation.

## Token budget policy

- Timeline events are summarized and capped; evidence excerpts are limited and truncated.
- A budget guard (default ~1500 tokens) drops low-priority timeline detail first (keeping the first
  and last step), then reduces evidence excerpts, always preserving severity/type/recommendations/
  caveats. Truncation is recorded in `truncated` + `truncation_notes`.
- A stable `source_context_hash` (SHA-256 of the canonical context) is stored to detect drift and
  avoid needless regeneration.

## Enable OpenAI locally

```sh
# apps/api/.env
INCIDENT_NARRATIVE_ENABLED=true
OPENAI_API_KEY=sk-...
OPENAI_INCIDENT_MODEL=gpt-4o-mini
```

Then `POST /incidents/{id}/narrative` returns `source = model` with token usage.

## Demo without OpenAI

Leave `OPENAI_API_KEY` empty. In the dashboard, open an incident, click **Generate AI Summary** —
the deterministic fallback renders, labeled "Deterministic fallback" and "Generated from minimized
incident context". Nothing is sent to OpenAI.

## Dashboard

The incident panel has an **AI Investigation Summary** section with a **Generate AI Summary** button.
It does not auto-generate; it calls the endpoint only on click and shows loading, error, and
fallback states.
