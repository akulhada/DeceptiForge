# DeceptiForge

## Context-aware deception for the AI era

DeceptiForge analyzes repository and organizational signals, proposes believable synthetic business assets, explains where they should be placed, and reconstructs an incident when those assets are touched.

**OpenAI Build Week category:** Developer Tools.

**Public video:** Pending public upload. Add the verified YouTube URL before submission.

**Hosted judge workspace:** Distributed to judges through the submission channel. Its URL and credentials are intentionally not committed to this repository.

## Problem

Conventional honeytokens can be useful, but a generic credential often looks disconnected from the repository, documentation, and business workflow where it appears. That problem is more visible when engineers, coding agents, retrieval systems, and operational services encounter the same internal material.

## Approach

DeceptiForge normalizes repository and organizational signals such as technologies, naming conventions, documentation zones, infrastructure indicators, databases, and AI-facing surfaces. It builds a context profile, ranks sensitive zones, recommends plausible placements, and evaluates synthetic assets for safety and believability.

When a registered trace is observed, deterministic services validate the event, minimize evidence, create a deduplicated alert, and reconstruct an incident timeline. The core flow is **Context → Decoy → Placement → Detection → Incident**.

## Implemented features

- Repository intelligence, naming-pattern inference, organization context, sensitive-zone ranking, and explainable placement reasoning.
- Template-constrained secret, document, and database-record decoy concepts with deterministic safety and believability assessment.
- Trace registration, signed monitoring ingestion, replay protection, normalized alerting, deduplication, deterministic incident reconstruction, and bounded evidence.
- Organization-scoped API keys, roles, permissions, audit records, payload limits, and Redis-backed distributed replay and rate-limit controls.
- A restricted judge workspace with a TTL-bound fictional organization, per-session quotas, safe export, and reset isolation.
- An Interactive Analysis Lab for development and test, with ten fictional structured-signal scenarios, comparison, and JSON or Markdown export.

Feature-flagged deployment workflows, database honey records, AI/browser/agent sensors, measured coverage, SIEM export, reliability, and capacity controls are disabled by default and covered with deterministic fakes where applicable. They are not a claim of production certification.

## Architecture

Next.js provides the dashboard; FastAPI hosts the deterministic security pipeline. PostgreSQL stores organization-scoped artifacts, while Redis provides distributed replay and rate-limit state in hardened modes. Reconstruction is queued so ingestion remains on the hot path. GPT is optional and cannot change authoritative security facts.

## How GPT-5.6 Is Used

The runtime integration is model-configurable. It can use an approved OpenAI model to turn an already verified, deterministic incident timeline into an analyst-readable narrative. Input is minimized and sanitized, output is schema-validated and bounded, and model failure, missing credentials, or invalid output falls back to a deterministic narrative.

The current checked-in default is `gpt-4o-mini`. If the Build Week recording uses GPT-5.6, set `OPENAI_INCIDENT_MODEL` to the approved GPT-5.6 model identifier and verify that exact model in the recording before claiming it on Devpost.

GPT does not assign severity, authorize deployment, accept monitoring events, alter evidence, choose an organization, or determine that an incident exists. Decoy generation is deterministic in the current implementation. A concrete demo example is a repository-trace touch that still produces its event, alert, severity, and incident when model access is disabled; only the analyst prose falls back.

## How We Built DeceptiForge with Codex

Codex accelerated codebase navigation, backend and frontend implementation, typed contract design, tests, migrations, tenant-isolation and signed-ingestion review, CI troubleshooting, dependency and container hardening, demo reliability, and documentation reconciliation.

The project author chose the security problem and context-aware deception thesis, required deterministic authority and human approval boundaries, rejected unsafe filesystem and hosted-demo shortcuts, selected the route model, and reviewed, revised, and tested generated changes. Codex was used to build and refine the project; it did not independently set product policy or security authorization.

## What We Added During OpenAI Build Week

The repository predates Build Week. The following verifiable extensions were added or substantially revised from July 13 through July 21, 2026:

- Platform-scope authorization separation, tenant-isolation coverage, signed-ingestion hardening, Redis fail-closed behavior, and production-shaped security tests.
- Interactive Analysis Lab and deterministic scenario comparison, added July 20 (`537fd80`, `fdc2123`).
- Dependency lockfiles, container and CI hardening, production topology validation, and operational worker readiness, added July 21 (`d561d80`, `f319daa`, `54a5157`).
- Explicit development, judge, staging, and production deployment modes; a restricted judge workspace; TTL-bound sandbox credentials; quotas; safe export; and isolated reset, added July 21 (`95903a5`, `3e7c0ef`, `5f93967`, `f4ade8c`, `5d327be`).

These commits are evidence of meaningful extension during the event period; they do not imply that the entire project was created during Build Week.

## Codex Session ID

Codex Session ID: `019f67eb-fa4d-77d0-ad70-eb034c57d246`

## Quick start

### Prerequisites

- Docker Desktop with Compose
- Node.js compatible with pnpm 9.15.4 and pnpm 9.15.4
- Python 3.12+ for local API tooling

```sh
git clone <repository-url>
cd DeceptiForge
cp .env.example .env
cp apps/api/.env.example apps/api/.env
cp apps/web/.env.example apps/web/.env.local
pnpm install
docker compose up --build -d
docker compose exec api alembic upgrade head
pnpm --filter @deceptiforge/web dev
```

Open `http://localhost:3000`. The development templates enable fictional demo data. Select **Run DeceptiForge Demo**, then confirm the context, placement, synthetic validation, event, alert, incident, and narrative. A local smoke check is `curl http://localhost:8000/health`.

For detailed environment, API, and deployment instructions, see [Development](docs/Development.md), [Pipeline API](docs/Api.md), and [Deployment](docs/Deployment.md).

## Judge testing

Use the hosted judge URL supplied through the submission channel, not localhost. Use a current Chromium browser.

1. Receive a dedicated organization ID and API key through a trusted channel.
2. Open the root workspace and choose a fictional scenario.
3. Inspect the inferred context, sensitive zones, placement reasoning, and synthetic decoy concept.
4. Trigger the controlled interaction, then inspect the deterministic event, alert, incident, and evidence summary.
5. Review the analyst narrative and its deterministic fallback boundary.
6. Reset the sandbox. Reset affects only that sandbox and does not restore spent quota.

Judge credentials are provisioned out of band, shown once, organization-bound, and time-limited. A sandbox expires with HTTP 410; an operator must issue a new one. See [Judge access runbook](docs/runbooks/JudgeAccess.md). The sandbox uses fictional data, accepts bounded structured signals only, disables production connectors, and never scans a local path or clones a repository.

The curated `/demo` story is development/judge-only. `/analysis-lab` is development/test-only and returns 404 elsewhere.

## Supported platforms

- **Tested:** macOS, Docker Desktop, Python 3.12, PostgreSQL 16, Redis 7, Node.js with pnpm 9.15.4, and Chrome for the local dashboard.
- **Reasonably supported:** current Chromium browsers on Linux and Windows, including Docker through WSL2.
- **Untested:** other operating systems and non-Chromium browsers. They are not claimed as certified.

## Security and privacy boundaries

Demo and judge assets are fictional and synthetic. API keys are organization-bound; tenant actors cannot mint platform or judge roles. Hardened modes require signed monitoring ingestion, distributed replay protection, and fail-closed Redis behavior. Evidence is minimized, and model input excludes raw payloads.

The development demo drives the deterministic pipeline in-process, not through a registered signed-monitor HTTP client. Signed ingestion is separately implemented and tested; the demo should not be represented as proving that boundary end to end.

## Current limitations

DeceptiForge is a controlled staging and judge-sandbox project, not a production-certified security service. Current limitations include no live GitHub/GitLab provider, no complete user OAuth/SSO implementation, no API-key rotation workflow, and no legal-hold implementation. GPT-assisted narratives are optional; all detection and incident decisions have deterministic fallback.

## Detailed documentation

- [Architecture](docs/Architecture.md), [Security model](docs/SecurityModel.md), and [Production readiness](docs/ProductionReadiness.md)
- [Development](docs/Development.md), [Deployment](docs/Deployment.md), and [Judge access](docs/runbooks/JudgeAccess.md)
- [Pipeline API](docs/Api.md), [Incident narrative](docs/IncidentNarrative.md), and [Disaster recovery](docs/DisasterRecovery.md)

## License

[MIT License](LICENSE)
