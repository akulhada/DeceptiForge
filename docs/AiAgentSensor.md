<!-- Purpose: document the AI agent activity sensor — enrollment, scoped sessions, minimized signed
activity ingestion, decoy-touch detection, deterministic scope violations, and retention. -->

# AI agent activity sensor

Detect when AI coding agents / MCP-enabled assistants interact with DeceptiForge decoys or access
assets outside the scope of the requested task. Registered agent sessions report minimized, signed
activity; deterministic rules raise explainable scope violations. Detect-only by default.

Disabled by default (`AGENT_SENSOR_ENABLED`); `AGENT_SENSOR_MODE=detect`. Explicit staging/production
enablement required.

## Supported adapters

- generic JSONL/stdin adapter (`app/agent_sdk/adapter.py::JsonlAdapter`)
- local filesystem/tool staging adapter (`LocalFsAdapter`)
- MCP-enabled development agent + generic signed agent-event API (same ingest path)

The `AgentAdapter` contract (`capabilities`, `normalize_event`, `health_check`) keeps vendor-specific
adapters isolated so future Codex / Claude Code / Copilot coding agent / Cursor integrations bind the
same interface. No undocumented private APIs; the wrapper observes/receives events and **never
executes the agent**.

## Observed data / excluded data

**Observed:** minimized activity metadata — event type, normalized repo-relative path + path class,
tool name, resource type, an optional resource-id hash, trace id, result status, and bounded safe
metadata (see [AgentPrivacy](AgentPrivacy.md)).

**Never stored or transmitted:** file contents, full commands or command output, prompts, model
reasoning / chain-of-thought, full conversations, terminal history, keystrokes, secrets. The wrapper
strips raw-content fields before an event leaves the machine, and the ingest schema has no
raw-content field.

## Flow

```
admin creates enrollment token -> wrapper enrolls (scoped signing secret + ingest key)
wrapper starts a scoped session (sanitized task summary + allowed/denied paths)
wrapper emits signed minimized events -> deterministic scope evaluation -> explainable violations
session completes -> deterministic content-free summary
```

Ingestion (`POST /monitoring/agent-events`) is `monitor-signature-v1` signed, replay-protected,
size-bounded, organization-bound, and idempotent (unique `session_id + external_event_id`). Revoked
sensors cannot report.

## Task scope

Each session carries a normalized scope: a sanitized/bounded task summary, normalized allowed/denied
path patterns, allowed/denied tools, and allowed resource types. Deterministic inference is primary
(keyword extraction + explicit user scope + policy overrides); an optional GPT scope suggestion is
advisory only and never the final enforcement decision. Raw conversation history is never persisted.

## Decoy-touch detection

Events are matched to registered decoys by **metadata** — trace id, decoy path, or resource-id hash —
against a bounded org decoy index built from the RAG/MCP/repository/database surfaces. A match emits a
`decoy_asset_touch` violation at high confidence; decoy contact strongly raises severity. Raw content
matching is never required.

## Deterministic scope violations

Violations (`out_of_scope_path_access`, `sensitive_file_access`, `decoy_asset_touch`,
`excessive_repository_breadth`, `unexpected_database_access`, `unexpected_network_access`,
`unexpected_mcp_resource_access`, `dependency_change_outside_scope`, `repeated_sensitive_exploration`,
`destructive_action_attempt`, `cross_repository_access`, `unapproved_tool_use`) are decided by a
bounded, incremental, fully deterministic engine (`app/services/agent_sensor/rules.py`). Each carries
the exact policy rule and a human-readable explanation. See [AgentScopePolicies](AgentScopePolicies.md)
for path classification and scoring. GPT may narrate an incident but never decides a violation or
severity.

## Detect-only + future blocking

Default is detect-only (`AGENT_SENSOR_MODE=detect`). Prevention interfaces (warn / require
confirmation / block denied tool / terminate) are designed for the future and **disabled by
default**; blocking is only allowed after explicit organization policy and documented support.

## Retention

Raw minimized activity events expire after `AGENT_EVENT_RETENTION_DAYS` (scheduled, batched,
org-scoped, auditable — `app/jobs/retention.py`). Scope violations and session summaries are retained
longer so summarized incident evidence outlives raw activity.

## Known limitations

First adapters are the generic JSONL/stdin and local staging adapters; vendor integrations are
future. Path classification is deterministic and pattern-based; unusual repository layouts may need
explicit policy paths. See [AgentPrivacy](AgentPrivacy.md) and [AgentAdapterSDK](AgentAdapterSDK.md).
