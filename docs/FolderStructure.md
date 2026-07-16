<!-- Purpose: map repository ownership boundaries. Responsibilities: help contributors place new modules predictably. Future modules: update this map when an approved top-level boundary is introduced. -->

# Folder Structure

```text
apps/
  api/                 FastAPI service, database infrastructure, and Alembic migrations
  extension/           Plasmo browser extension
  web/                 Next.js browser application
docs/                  Architecture, development, and contribution guidance
packages/              Future shared, versioned packages
```

Within `apps/api/app`:

```text
api/           HTTP handler modules
config/        Validated environment-derived settings
core/          Cross-cutting backend primitives
database/      SQLAlchemy engine, sessions, and declarative base
dependencies/  Reusable FastAPI dependencies
middleware/    Transport middleware
models/        SQLAlchemy persistence models
prompts/       Versioned AI prompt assets
repositories/  Non-trivial persistence queries
routes/        Router composition
schemas/       Pydantic request and response contracts
services/      Application use-case orchestration
utils/         Small stateless utilities
websocket/     Realtime transport modules
```

Within `apps/web`, use `app/` for routes, `components/` for presentation, `services/` for API clients, `store/` for genuine client state, and `types/` for shared frontend types. Within `apps/extension/src`, use `background/` and `contents/` only when a feature needs those browser execution contexts.
