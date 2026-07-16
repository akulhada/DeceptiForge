<!-- Purpose: explain local development. Responsibilities: document the supported setup and verification commands. Future modules: add debugging, seed-data, and deployment instructions when they exist. -->

# Development

## Prerequisites

- Node.js compatible with pnpm 9
- pnpm 9
- Python 3.12 or newer
- Docker Desktop for local PostgreSQL and API containers

## Setup

```sh
cp .env.example .env
cp apps/api/.env.example apps/api/.env
cp apps/web/.env.example apps/web/.env.local
cp apps/extension/.env.example apps/extension/.env
pnpm install
docker compose up --build
```

For host-run API development, make `apps/api/.env` use `localhost` as the database host and ensure its password matches root `.env`.

## Commands

```sh
pnpm dev
pnpm build
pnpm lint
pnpm test
pnpm typecheck
pnpm format:check
```

Python checks run from `apps/api` after installing the development extra:

```sh
python -m pip install -e '.[dev]'
ruff check .
black --check .
mypy app
pytest
```

Apply migrations with `alembic upgrade head`. Create a revision only after an approved SQLAlchemy model change.
