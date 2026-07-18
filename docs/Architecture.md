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

## Security posture

Configuration is environment-derived; secrets are excluded from Git. CORS is deny-by-default unless an origin allow-list is configured. The extension requests no browser permissions or host access. New AI, extension, or data-collection capabilities require a threat model and least-privilege permission design before implementation.

## Decision log

Architecture decisions that change a long-lived boundary should be recorded under `docs/adr/` before implementation.
