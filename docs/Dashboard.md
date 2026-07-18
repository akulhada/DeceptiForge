<!-- Purpose: document the demo dashboard and how to run it. Responsibilities: describe setup, the
demo flow, and the API it consumes. Future modules: expand as live onboarding replaces the seed. -->

# Demo Dashboard

A thin Next.js console that tells the DeceptiForge story end to end in under three minutes:
scan → context → placements → decoys → validation → detection → alert → incident.

It reads one aggregate endpoint (`GET /demo/state`) and drives the story with two actions
(`POST /demo/seed`, `POST /demo/simulate-detection`). All demo endpoints are demo-only scaffolding.

## Sections

1. **Overview** — decoy, tripwire, event, alert, incident counts and a coverage estimate.
2. **Repository Profile** — languages, frameworks, services, package managers, cloud/DB, naming, risks.
3. **Placement Plan** — ranked recommendations (target, type, priority, confidence, risk, reasoning).
4. **Decoy Generation** — decoy cards with type, placement, template, trace id, validation, safety.
   Secret values are masked by default (reveal per card).
5. **Validation Reports** — believability/safety scores, accept/warn/reject, failed checks, fixes.
6. **Monitoring Events** — raw detections with trace, monitor, location, time, minimized evidence.
7. **Alerts** — normalized alerts with severity, source, event count, recommended actions.
8. **Incidents** — reconstructed timeline, involved decoys/surfaces, deterministic hypothesis, actions.

## Run it

Terminal 1 — API (Postgres):

```sh
cp apps/api/.env.example apps/api/.env      # CORS_ORIGINS already allows http://localhost:3000
docker compose up -d postgres               # from the repo root
cd apps/api
pip install -e '.[dev]'
alembic upgrade head
uvicorn app.main:app --reload               # http://localhost:8000
```

Terminal 2 — dashboard:

```sh
cp apps/web/.env.example apps/web/.env       # NEXT_PUBLIC_API_URL=http://localhost:8000
cd apps/web
pnpm install
pnpm dev                                     # http://localhost:3000
```

## Demo script (2–3 minutes)

1. Open `http://localhost:3000`. Click **Seed demo data**.
2. **Overview** fills in: 1 decoy, 1 accepted, 1 active tripwire, repository coverage 100%.
3. **Repository Profile** — the engine learned `acme-payments`: Python, FastAPI, services, AWS, CI/CD.
4. **Placements** — ranked locations (for example `.env.example`) with reasoning.
5. **Decoys** — a schema-constrained secret decoy with a masked value and a trace id.
6. **Validation** — believability and safety scores accept the decoy.
7. Click **Simulate detection**. A monitor event, alert, and incident appear.
8. **Incidents** — a HIGH `repository_exposure` incident with a timeline, evidence, deterministic
   hypothesis, and response actions.

## Seed without a server

For an offline check of the pipeline (no server, no Postgres):

```sh
cd apps/api
python -m scripts.demo            # or: python -m scripts.demo /path/to/repo
```

## API flow used by the dashboard

```text
POST /demo/seed ─► scan → plan → generate → evaluate   (returns full state)
GET  /demo/state ─► aggregate: profile, context, placements, decoys, reports, events, alerts, incidents
POST /demo/simulate-detection ─► trace hit → event → alert → incident   (returns full state)
```

These wrap the product endpoints documented in [Api.md](Api.md); they add no engine logic.

## Screenshots

<!-- Add captured screenshots here for the submission:
docs/images/dashboard-overview.png
docs/images/dashboard-incident.png -->

_Overview and incident screenshots go here for the submission._

## Notes

- Demo endpoints scan a bundled fixture at `apps/api/app/demo/acme-payments`; the dataset is
  deterministic, so the demo is repeatable.
- The demo intentionally generates a small decoy set for a clear, stable story; richer multi-surface
  decoys are a later enhancement.
