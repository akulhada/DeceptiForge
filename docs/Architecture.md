<!-- Purpose: describe the repository's technical boundaries. Responsibilities: record current infrastructure decisions and extension points. Future modules: add bounded-context and deployment decisions as they are approved. -->

# Architecture

## Current shape

DeceptiForge is a pnpm monorepo with independently deployable applications:

- `apps/web` is a Next.js browser application shell.
- `apps/api` is a FastAPI service with SQLAlchemy and Alembic infrastructure.
- `apps/extension` is a Plasmo browser-extension shell.
- PostgreSQL is the only local infrastructure service.

The API owns persistence. Browser applications communicate with it through explicit HTTP contracts; they do not access PostgreSQL directly.

## Backend boundaries

`routes` composes HTTP routers, `api` will contain handlers, `services` will hold use-case orchestration, and `repositories` will contain non-trivial persistence queries. SQLAlchemy models and Pydantic schemas remain separate so database representation does not become the public API contract.

The current deterministic pipeline is delivered as vertical slices across domain models, migrations,
repositories, services, routes, and tests. New features should preserve these boundaries.

External systems (GitHub, PostgreSQL, RAG vector stores, MCP servers) are reached only through
narrow connector **ports** with encrypted secrets; each port ships a deterministic fake adapter so
the full lifecycle is exercised in CI without paid services, and a concrete provider adapter binds
the same interface in production. Side-effecting deployments run off the request path via idempotent
jobs (unique per deployment+type), and monitoring events arrive through signed, replay-protected,
minimized ingestion. The AI tripwire slice (RAG/MCP) follows this pattern — see
`docs/AiTripwires.md`.

The browser AI-paste sensor (`apps/extension`, Chromium MV3) extends monitoring to the endpoint: a
minimal-permission extension matches DeceptiForge trace markers locally against irreversible hashed
tokens and reports only signed, minimized events to the same `monitor-signature-v1` ingestion path.
Per-install sensors carry a scoped credential provisioned via one-time enrollment tokens, and the
signing secret stays in the background service worker. Detection logic is factored into pure,
node-testable modules with thin DOM/background adapters. See `docs/BrowserAiSensor.md`.

The AI agent activity sensor extends the same signed-ingestion pattern to coding agents: a wrapper/
CLI (`app/agent_sdk`) reports minimized, signed activity for a scoped session, and a deterministic,
bounded engine (`app/services/agent_sensor`) classifies paths, resolves decoy touches by metadata,
and raises explainable scope violations with deterministic severity. Path normalization is
security-critical (rejects traversal/encoded/absolute). Detect-only by default. See
`docs/AiAgentSensor.md`.

## Security posture

Configuration is environment-derived; secrets are excluded from Git. CORS is deny-by-default unless an origin allow-list is configured. The extension requests only minimal MV3 permissions (storage, alarms) with host access scoped to the supported AI domains, and runs under a locked CSP with no eval or remote code (see `docs/ExtensionDeployment.md`). New AI, extension, or data-collection capabilities require a threat model and least-privilege permission design before implementation.

## Decision log

Architecture decisions that change a long-lived boundary should be recorded under `docs/adr/` before implementation.
