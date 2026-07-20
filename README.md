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
- [Performance architecture](docs/PerformanceArchitecture.md) · [SLOs](docs/ServiceLevelObjectives.md) · [Load testing](docs/LoadTesting.md) · [Capacity planning](docs/CapacityPlanning.md) · [Tenant limits](docs/TenantLimits.md)

## Current status

Controlled-staging grade, not a finished multi-tenant SaaS — see
[Production readiness](docs/ProductionReadiness.md). Local-path repository scanning and all `/demo/*`
routes are development/demo-only (gated by `DEMO_ENABLED`/`AUTH_ENABLED`, off by default). Advanced
deception surfaces and reliability features ship **disabled by default** behind feature flags and are
exercised in CI against deterministic fakes — never live third-party services.

**Implemented & tested (core).** Repository scan → context profiling → decoy generation → monitoring
→ alerting → incident reconstruction → optional AI narrative → coverage estimate; organization-scoped
persistence and incident upsert (no global delete/reinsert); hashed, scoped, revocable API keys;
signed (`monitor-signature-v1`), replay-protected, size-bounded monitoring ingestion; Redis-backed
distributed rate limiting and replay store; evidence encryption at rest; scheduled advisory-locked
retention/lifecycle jobs. Covered by the backend suite plus live-PostgreSQL and live-Redis CI jobs.

**Implemented behind default-off feature flags (controlled environments).** Each is CI-tested against
deterministic fakes; no paid/live provider is contacted:

- Decoy deployment approval + lifecycle — `docs/DecoyDeployment.md` (live GitHub App is a fake adapter — see Planned).
- Database honey records (PostgreSQL) — `docs/DatabaseHoneyRecords.md`.
- AI tripwires (RAG / MCP) — `docs/AiTripwires.md`, `docs/AiDataHandling.md`.
- Browser AI-paste sensor (Shadow AI) — `docs/BrowserAiSensor.md`, `docs/BrowserPrivacy.md`.
- AI agent activity sensor (scope violations) — `docs/AiAgentSensor.md`, `docs/AgentScopePolicies.md`.
- Measured coverage engine + placement optimization — `docs/CoverageEngine.md`, `docs/PlacementOptimization.md`.
- SIEM/SOAR export + incident export — `docs/SecurityIntegrations.md`, `docs/IncidentExport.md`.
- Multi-region reliability + disaster recovery — `docs/DisasterRecovery.md`, `docs/RestoreDrills.md`.

**Partially implemented.** The API-key/organization boundary has no key rotation. The demo path shows
a lightweight weighted coverage estimate; the flagged measured coverage engine is the accurate path.

**Planned / not implemented.** Real user identity (OAuth/SSO and full RBAC beyond role→scope); live
GitHub/GitLab App provider integration (currently a fake adapter); API-key rotation. No production
certification is claimed — certify via a staging restore drill + regional rehearsal
(see [Staging verification](docs/checklists/StagingVerification.md)).
