<!-- Purpose: document AI tripwire data minimization — what event data is accepted, what is stored,
what is never persisted or logged, and how ingestion is trusted. -->

# AI tripwire data handling

AI tripwire monitoring is designed so that **no raw AI content is ever persisted or logged**. This
document is the contract for event ingestion and storage.

## Trusted, signed ingestion

Events are posted to `POST /ai-tripwire-events` and must be tamper-evident and replay-protected,
reusing the monitor signing path:

- HMAC signature over method/path/organization/monitor/timestamp/nonce/body-hash
  (`MonitorCredentialService.verify_request`), enforced when signing is required;
- single-use nonce + timestamp clock-skew bound (the replay guard) — a reused nonce is rejected
  (409);
- organization scoping (a monitor credential from another org is rejected);
- the event's `trace_id` must match a deployment in the caller's organization whose monitoring is
  **active**; otherwise the event is rejected (404 unknown trace / 409 monitoring inactive).

## What is stored

Per `MinimizedAiEvent` / `AiTripwireEventRecord`, only:

- deployment id, trace id, surface type, event type
- source identity (bounded), monitor identity (bounded)
- confidence
- bounded, minimized metadata
- observed timestamp

## What is never stored or logged

`minimize_metadata` (`app/services/ai_tripwire/minimize.py`) drops forbidden keys and oversized
values before anything is written. The system never stores or logs:

- full prompts or model inputs
- retrieved documents or chunks
- full model output / completions / answers
- raw embeddings or vectors
- messages, conversations, or histories
- connector secrets
- raw customer content

Metadata is bounded: forbidden keys removed, values over 512 chars dropped as likely raw content,
at most 12 fields, each truncated to 120 chars, serialized to at most 1024 chars. Audit records
(`AiTripwireAuditRecord`) store only event types and safe metadata — never secrets or raw content.

## Presentation

The dashboard renders only minimized event metadata and labels AI-native exposure deterministically.
Any GPT narrative is presentation-only and shown separately from the deterministic evidence; GPT
never assigns severity or decides deployment safety.

## False positives

Trace markers are distinctive and events are only trusted from signed monitors, so a stray textual
match is not treated as ingestion on its own. See [AI tripwires](AiTripwires.md#trace-design).
