<!-- Purpose: document the agent adapter contract, the deceptiforge-agent CLI, signing, and the
bounded offline queue. -->

# Agent adapter SDK + CLI

The SDK (`app/agent_sdk/`) lets a coding-agent wrapper report minimized, signed activity. It observes
or receives events; it never executes the agent.

## Adapter contract

`AgentAdapter` (Protocol): `capabilities()`, `normalize_event(raw) -> NormalizedEvent`,
`health_check()`. `normalize_event` enforces the event-type allowlist and **strips any raw-content
field** (file content, command output, prompts, reasoning, sql, …) before the event leaves the
machine. Shipped adapters:

- `JsonlAdapter` — generic JSONL/stdin events (`{id, event_type, path?, tool?, ...}`).
- `LocalFsAdapter` — staging adapter mapping local `read/list/write/create/delete/search/tool`
  actions to minimized events. Reads only paths and action types, never file contents.

Vendor-specific adapters stay isolated behind this contract.

## Client + signing

`AgentClient` signs every request with the sensor secret (`monitor-signature-v1`: method/path/org/
sensor/timestamp/nonce/body-hash HMAC), posts session start + minimized events, and retries safely.
The transport is injectable for testing. The signing secret stays in the wrapper process and is never
placed in a URL.

## Bounded offline queue

When the backend is unreachable, only already-minimized events are queued (bounded to the queue
limit, oldest dropped), deduped by `external_event_id` so a retry never double-reports, and flushed
once connectivity returns (a `409` duplicate/replay is treated as delivered). Raw content is never
queued.

## CLI

```bash
# credentials from the environment: DECEPTIFORGE_URL / _ORG_ID / _API_KEY / _SENSOR_ID / _SENSOR_SECRET
python -m app.agent_sdk.cli start  --session-id S --agent-type claude-code --task "Fix navbar" --allow "apps/web/**"
echo '{"id":"e1","event_type":"file_read","path":"apps/web/navbar.tsx"}' | \
  python -m app.agent_sdk.cli event --session-id S --adapter jsonl
python -m app.agent_sdk.cli finish --session-id S
```

The CLI does not run the agent; it only reports observed events.

## Enrollment

An admin creates a one-time short-lived enrollment token (`POST /agent-sensors/enrollment-tokens`);
the wrapper exchanges it (`POST /agent-sensors/enroll`) for a sensor identity, a scoped signing
secret, and a scoped ingest API key (the `agent_sensor` role: start sessions, fetch scope policy,
ingest events — nothing else). The token is invalidated on use.
