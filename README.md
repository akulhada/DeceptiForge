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
