<!-- Purpose: Introduce the repository and its local development workflow. Responsibilities: document shared commands and application boundaries. Future modules: API, web, browser extension, and deployment runbooks. -->

# DeceptiForge

DeceptiForge is a context-aware deception platform for AI-era security. It generates stack-aware decoys and captures unauthorized access by people and AI agents.

## Workspace

- `apps/api` — FastAPI service and database migrations.
- `apps/web` — Next.js application.
- `apps/extension` — Plasmo browser extension.
- `packages/*` — shared, versioned TypeScript packages.

## Local development

```sh
cp .env.example .env
docker compose up -d postgres
pnpm install
pnpm dev
```

Module-specific setup is documented as each application is added.

## Quality checks

```sh
pnpm lint
pnpm test
pnpm format:check
```

## Demo

With `DEMO_ENABLED=true` (development/demo only), open the dashboard and click **Run DeceptiForge
Demo**. It runs the full pipeline — repository analysis → context → placements → decoys →
validation → tripwires → detection → alert → incident → optional AI summary → coverage — with
per-step status, then shows a weighted coverage estimate. A run is exportable as Markdown/JSON. See
[Dashboard](docs/Dashboard.md) and [Pipeline API](docs/Api.md).

## Documentation

- [Architecture](docs/Architecture.md)
- [Development](docs/Development.md)
- [Contributing](docs/Contributing.md)
- [Folder structure](docs/FolderStructure.md)
- [Production readiness](docs/ProductionReadiness.md) · [Security model](docs/SecurityModel.md) · [Preflight checklist](docs/checklists/ProductionPreflight.md)
- [Dashboard](docs/Dashboard.md) · [Pipeline API](docs/Api.md) · [Incident narrative](docs/IncidentNarrative.md) · [Production boundary](docs/ProductionBoundary.md)

## Production Hardening Roadmap

The current build is a hackathon MVP. **Local-path repository scanning and all `/demo/*` routes are
development/demo-only** (gated by `DEMO_ENABLED`/`AUTH_ENABLED`, off by default). The following are
explicitly future work, not solved here:

- **Auth & authorization** — the API-key/org-id boundary is a stub, not user management/OAuth/RBAC.
- **Real tenant identity** — pipeline artifacts are organization-scoped, but the API-key binding
  remains a stub; real tenant provisioning, identity, and authorization are future work.
- **Repository integrations** — replace local filesystem paths with GitHub/GitLab app installs and
  repository ids; never accept arbitrary server paths in production.
- **Durable monitor ingestion & dedup** — current monitoring/alerting rebuild per request; needs a
  durable queue and persistent deduplication.
- **Repository-scoped incident persistence** — incidents currently filter by involved decoys as a
  fallback; add an incident scoping column.
- **Distributed rate limiting & audit history** — current limits are single-process and MVP-scoped.
- **Full Coverage Engine** — the current coverage is a lightweight demo estimate, not a measured
  protected-vs-attack-surface metric.
- **CI/CD & deployment hardening** — pipelines, secrets management, migrations, and observability.
- **Decoy deployment approval + lifecycle** — reviewable, reversible repository decoys through a
  controlled branch + PR, with monitoring activated only after a verified merge. Disabled by
  default; the live GitHub App adapter is not yet implemented (see `docs/DecoyDeployment.md`).
- **Database honey records (PostgreSQL)** — approved, transactional synthetic rows as database
  tripwires, monitored only after verification and reversible by exact owned-row deletion. Disabled
  by default; the real connector adapter is CI-tested against an ephemeral database
  (see `docs/DatabaseHoneyRecords.md`).
- **AI tripwires (RAG / MCP)** — inert synthetic decoy documents and MCP resources/configs deployed
  into approved collections/servers, monitored only after verification via signed, minimized events,
  with deterministic AI-native exposure classification and reversible owned-asset retirement.
  Disabled by default; RAG/MCP adapters are CI-tested with deterministic fakes — no paid AI services
  (see `docs/AiTripwires.md`, `docs/AiDataHandling.md`).
- **Browser AI-paste sensor (Shadow AI)** — a minimal-permission Chromium extension that detects
  DeceptiForge trace markers pasted into AI tools via local hashed matching, distinguishes approved
  from shadow AI destinations, and reports only signed, minimized evidence (never pasted text,
  prompts, or AI responses). Disabled by default (see `docs/BrowserAiSensor.md`,
  `docs/BrowserPrivacy.md`).
- **AI agent activity sensor (scope violations)** — registered agent sessions report minimized,
  signed activity; deterministic, explainable rules flag out-of-scope, sensitive, and decoy access
  across repository/MCP/RAG/database surfaces. Detect-only by default; never stores file contents,
  prompts, command output, or model reasoning (see `docs/AiAgentSensor.md`,
  `docs/AgentScopePolicies.md`, `docs/AgentPrivacy.md`, `docs/AgentAdapterSDK.md`).
- **Measured coverage engine + placement optimization** — deterministic, risk-weighted deception
  coverage computed from real active controls across every surface (not decoy count), with explicit
  unknown/low-confidence handling, immutable snapshots + trends, blind-spot detection, and ranked
  next-best placements. Disabled by default; GPT never scores (see `docs/CoverageEngine.md`,
  `docs/CoverageMethodology.md`, `docs/PlacementOptimization.md`).
