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

## Documentation

- [Architecture](docs/Architecture.md)
- [Development](docs/Development.md)
- [Contributing](docs/Contributing.md)
- [Folder structure](docs/FolderStructure.md)
