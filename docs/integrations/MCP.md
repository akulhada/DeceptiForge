<!-- Purpose: document the MCP connector — adapter interface, inert resource format, allowlist,
verification, and the staging fake adapter. -->

# MCP connector

DeceptiForge deploys inert synthetic decoy resources/configs into an organization's approved MCP
server and detects access via signed events. Disabled by default (`MCP_CONNECTORS_ENABLED`,
`AI_TRIPWIRE_DEPLOYMENT_ENABLED`).

## Adapter interface

`McpConnectorAdapter` (`app/services/ai_tripwire/connectors.py`):

- `test_connection`, `list_resources`, `health_check`
- `deploy_resource` — idempotent by resource URI
- `verify_resource` — reads back existence, content-hash match, and trace presence
- `retire_resource` — deletes only when the content hash still matches (else reports drift)

## Inert resource format

Decoy resources use the reserved scheme `deceptiforge://decoy/{kind}/{token}` and carry a structured
metadata trace. They are declarative only:

- **no** executable tools, destructive actions, or hidden behavior changes
- **no** real credentials or real production endpoints
- **no** prompt-injection instructions

Content safety validates every resource (URI scheme, injection/executable patterns) before preview
or deployment. An MCP server allowlist (`AI_TRIPWIRE_ALLOWED_MCP_SERVERS`) restricts which servers a
connector may reference; an empty allowlist permits any server in development only.

## First implementation

The shipped adapter is `FakeMcpAdapter`, a deterministic in-memory MCP server for local development
and CI — **no external MCP server is contacted in tests**. For a first real integration a controlled
staging MCP server is acceptable. Concrete wiring binds the same interface in `build_mcp_adapter`
and the worker.

**Staging limitation:** resource listing/read semantics vary by MCP server; verify the specific
server exposes stable resource ids and a read-back path before relying on drift detection.

## Detection events

Trusted, signed access events (`resource_listed`, `resource_read`, `resource_referenced`,
`config_loaded`, `uri_requested`, `metadata_copied`, `agent_touched`) are posted to
`POST /ai-tripwire-events`. Only minimized metadata is stored — never full agent prompts or
conversation histories. See [AI data handling](../AiDataHandling.md).
