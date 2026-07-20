<!-- Purpose: the agent sensor privacy contract — exactly what is and is not observed/stored, signed
ingestion, and audit boundaries. -->

# Agent sensor privacy

The agent activity sensor is designed so that **no raw agent content is ever stored or transmitted**.

## Principles

- Observe only registered agent sessions; require explicit organization policy.
- Signed, replay-protected event ingestion; store minimized metadata only.
- Do not store complete prompts, complete source files, or model reasoning / chain-of-thought.
- Do not execute repository code. Do not block agent actions by default.
- Deterministic rules decide scope violations; GPT may explain but never decides severity or policy
  violations.
- Every event is organization-scoped and auditable.

## What is stored per event

Only: sensor id, session id, event type, repository id (optional), normalized repo-relative path +
deterministic path class, tool name, resource type, an optional **resource-id hash**, trace id,
decoy id (when matched), result status, bounded safe metadata, correlation id, and the observed
timestamp.

## Never stored, transmitted, or logged

File contents, full commands or command output (stdout/stderr), prompts, model reasoning /
chain-of-thought, full conversations, terminal history, keystrokes, database query text, secrets, or
raw credentials. The wrapper strips raw-content fields before sending
(`app/agent_sdk/adapter.py`); the ingest minimizer drops them again server-side
(`app/services/agent_sensor/minimize.py`); the ingest schema has no raw-content field. Task summaries
are sanitized and bounded — never a raw conversation.

## Signed, replay-safe ingestion

`POST /monitoring/agent-events` requires `monitor-signature-v1` (sensor id + timestamp + nonce + body
hash + signature), passes the distributed replay guard, is size-bounded
(`AGENT_SENSOR_EVENT_MAX_BYTES`), organization-bound, and idempotent per `external_event_id`. The
scoped ingest key is provisioned per install and revoked with the sensor.

## Audit

Enrollment, revoke, credential rotation, policy create/update/delete, session start/complete, event
accept/reject, signature/replay failure, violation generation, decoy touch, and cross-org denials are
audited (`agent_sensor_audit`). Audit rows never contain prompts, file contents, command output,
model reasoning, secrets, or terminal history.

## Retention

Raw activity events expire before violations and session summaries, so summarized incident evidence
outlives raw activity. Cleanup is org-scoped, batched, scheduled, and auditable.

A legal/privacy review is recommended before enterprise rollout.
