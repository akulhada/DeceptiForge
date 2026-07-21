# DeceptiForge

## Context-aware deception for the AI era

DeceptiForge analyzes how an organization works, creates believable synthetic business assets,
places them where attackers and AI agents are likely to look, and reconstructs the incident when
those assets are touched.

**Submission links:** public demo video and hosted judge sandbox are not published from this
repository. Do not submit until their public URLs and restricted test access have been verified.

## Problem and approach

Generic honeytokens can look detached from the code, documentation, and business workflows around
them. DeceptiForge derives repository context, naming patterns, sensitive paths, and placement
signals before producing schema-constrained synthetic decoys. The product then validates safety and
believability, records a tripwire touch, creates a deterministic alert, and reconstructs a
minimized-evidence incident timeline.

The core flow is **Context → Decoy → Placement → Detection → Incident**. The built-in development
demo uses fictional data only and demonstrates this complete backend-driven flow.

## Implemented capabilities

- Repository intelligence, naming-pattern inference, organization context, and placement reasoning.
- Deterministic template-constrained secret, document, and database-record decoys with safety and
  believability checks.
- Trace monitoring, normalized alerting and deduplication, deterministic incident reconstruction,
  coverage estimates, and a tenant-scoped dashboard.
- Organization-scoped API keys, permissions, audit records, evidence minimization, replay controls,
  bounded payloads, and optional Redis-backed protections.
- Development-only controlled demo orchestration. Demo routes are mounted only when
  `APP_ENV=development` and `DEMO_ENABLED=true`.

Feature-flagged modules such as deployment workflows, database honey records, AI/browser/agent
sensors, measured coverage, SIEM export, reliability, and capacity controls are documented in the
links below. They are disabled by default and exercised with deterministic fakes. They are not a
claim of production certification.

## Interactive Analysis Lab

An authenticated, organization-scoped **development and test** route (`/analysis-lab`) that turns
the single prepared demo into a testable prototype. It is an internal fixture surface, not a
product capability: it returns a real 404 in the hosted judge environment and in production, on
both the frontend and the API, rather than merely being hidden from navigation. Paste or edit **structured repository signals** as JSON (languages,
frameworks, services, databases, naming patterns, infrastructure, documentation, secret locations,
AI surfaces), pick one of **ten prepared fictional scenarios** (fintech, SaaS/CRM, healthcare,
e-commerce, ML/RAG, Kubernetes microservices, monorepo, sparse, conflicting, high-risk secrets+AI),
and run DeceptiForge's **deterministic** analysis: inferred context profile, vocabulary/naming,
ranked sensitive zones, ranked placement recommendations, layered confidence, and explainable
warnings — each showing which input signals drove it. Compare two scenarios side by side and export
the result as JSON or Markdown.

Boundary: the lab accepts only structured signals. It **does not scan a filesystem, clone a
repository, execute code, or call GPT**, and it does not persist input or results. Path-like strings
are descriptive metadata only and are never opened. The endpoint is
`POST /api/v1/analysis/preview` (permission `analysis:preview`; viewer/analyst/admin/owner; sensors
and judges excluded), authenticated and org-scoped, with payload and rate limits — see
[Pipeline API](docs/Api.md).

## Architecture

Next.js provides the dashboard. FastAPI hosts the API and deterministic security pipeline.
PostgreSQL persists tenant-scoped artifacts; Redis is used for distributed replay and rate-limit
stores when configured. Expensive reconstruction is queued. GPT is optional and isolated from the
authoritative detection path.

## GPT runtime use

The current implementation uses a configurable OpenAI model for an **AI-assisted analyst summary**
of an already reconstructed incident. It receives bounded, sanitized timeline context; output is
validated and a deterministic fallback is returned when the model, credential, or response is
unavailable. In the demo, a repository trace touch still produces its event, alert, severity, and
incident if the model is disabled.

GPT does not authorize access, approve deployments, assign severity, alter evidence, select an
organization, accept monitoring events, or decide whether an incident exists. Decoy generation is
deterministic in the current implementation; it does not require GPT.

## How We Built DeceptiForge with Codex

Codex acted as a development collaborator for repository navigation, domain/API and frontend work,
test generation, authorization and signed-ingestion review, migrations, CI diagnosis, error
handling, and demo reliability. Generated changes and recommendations were inspected, tested,
revised, and validated by the author.

The author selected the problem and product concept, kept deterministic security logic
authoritative, set approval and safety boundaries, chose the demo flow, and made the final tradeoffs
between realism, privacy, safety, and delivery time. Codex did not autonomously set product policy
or authorize deployment. GPT is a runtime product capability; Codex was a development tool.

Codex Session ID must be added manually from `/feedback` in the primary development thread before
submission. It is intentionally not invented or stored as a placeholder here.

## Quick start and judge testing

Prerequisites: Docker Desktop, Python 3.12+, Node.js compatible with pnpm 9.15.4, and pnpm 9.15.4.
The verified local path is Docker Desktop on macOS with Chrome; the web dashboard is expected to
work in current Chromium browsers on Linux and Windows, but those environments have not been
certified here.

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

Open `http://localhost:3000`. With the development templates, `DEMO_ENABLED=true` and
`NEXT_PUBLIC_DEMO_MODE=true` expose the fictional demo. Select **Run DeceptiForge Demo** and
confirm repository context, placement reasoning, synthetic validation, event, alert, incident,
coverage, and an AI-assisted or deterministic-fallback narrative. Refreshing the page is safe.
`POST http://localhost:8000/demo/reset` clears only the demo organization.

### Routes

| Route | What it is | Where it exists |
| --- | --- | --- |
| `/` | the live restricted judge and testing workspace | development and the hosted judge environment; elsewhere it is the ordinary authenticated tenant workspace |
| `/demo` | the curated fictional story used in the video | development and the hosted judge environment, with `NEXT_PUBLIC_DEMO_MODE=true` |
| `/analysis-lab` | internal deterministic fixtures | development and test only |

There is no separate `/judge` flow. The root route serves the judge workspace directly, so there is
no second component duplicating its state, and nothing to redirect.

All judge and demo data is fictional. Arbitrary filesystem scanning is unavailable: the workspace
accepts bounded structured signals only, and path-like values inside them are descriptive metadata
that the backend never opens. Production integrations and connectors are disabled in the sandbox.

**Judges use the hosted URL, not localhost.** The `localhost` instructions above are for
contributors running the stack themselves. Hosted links are published with the submission rather
than committed here, since no judge credentials belong in this repository.

### Judge workspace access

Judge access requires a server-verified credential; there is no anonymous fallback. Each judge gets
an isolated, time-limited sandbox with its own organization, so no judge can see another's work:

```sh
cd apps/api
python scripts/provision_judge_sandbox.py            # judge sandbox: org id + key + expiry
python scripts/provision_judge_sandbox.py --demo-credential   # demo writes, hosted only
```

Each prints its credential once. Pass `--ttl-hours` to cover the full evaluation window (the
default is 8 hours, which suits a single sitting) — see
[JudgeAccess](docs/runbooks/JudgeAccess.md). The `judge` and `demo` roles cannot be minted through
tenant administration, and neither can reach tenant administration, platform operations, or the other's
data. Reading `/demo` needs no credential; changing what every other viewer sees does.

For detailed setup, API, security, and deployment instructions, use the linked durable documents.
No judge credentials, production secrets, or customer data belong in this repository.

## Security, privacy, and limitations

All demo assets are fictional and synthetic. The local demo trigger uses the real deterministic
pipeline but currently invokes it inside the development-only API rather than through a registered
signed monitor HTTP client. Signed monitoring ingestion, replay rejection, and monitor credentials
exist separately and remain the production boundary. A signed-demo-trigger integration is required
before claiming the demo proves that boundary end to end.

This repository is a controlled-staging project, not a production-certified security service.
Current limitations include no live GitHub/GitLab provider, no full user OAuth/SSO implementation,
and no API-key rotation. See [Production readiness](docs/ProductionReadiness.md).

## Supported Platforms

- Tested: macOS, Docker Desktop, Python 3.12, PostgreSQL 16, Redis 7, Node.js with pnpm 9.15.4,
  and Chrome for the local dashboard.
- Expected but not certified: current Chromium browsers on Linux and Windows, including Docker via
  WSL2.

## Documentation and license

- [Architecture](docs/Architecture.md), [Development](docs/Development.md), and
  [Dashboard](docs/Dashboard.md)
- [Pipeline API](docs/Api.md), [Security model](docs/SecurityModel.md), and
  [Production boundary](docs/ProductionBoundary.md)
- [Incident narrative](docs/IncidentNarrative.md), [Performance architecture](docs/PerformanceArchitecture.md),
  [Capacity planning](docs/CapacityPlanning.md), and [Disaster recovery](docs/DisasterRecovery.md)
- [MIT License](LICENSE)
