<!-- Purpose: document the pipeline API and how to run it. Responsibilities: describe endpoints,
the end-to-end flow, and local setup. Future modules: expand as authentication, tenancy, and the
dashboard are added. -->

# Pipeline API

A thin HTTP surface over the deterministic engine layer. It scans a repository, plans and generates
decoys, validates believability and safety, ingests monitoring events, and reconstructs incidents.
Each artifact is persisted; engines are unchanged and hold the detection logic.

## Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/repositories/scan` | Scan a local path → stored `RepositoryIntelligenceProfile` |
| GET | `/repositories/{id}/profile` | Read a stored profile |
| POST | `/placements/plan` | Build context + placement plan for a repository |
| POST | `/decoys/generate` | Generate a decoy plan from the latest placement plan |
| POST | `/validation/evaluate` | Score believability/safety for each decoy |
| POST | `/monitoring/events` | Feed a value at a surface; register decoys, detect, alert |
| GET | `/alerts` | List normalized alerts |
| GET | `/incidents` | List reconstructed incidents |
| GET | `/api/v1/analysis/scenarios` | List prepared fictional Interactive Demo Lab scenarios |
| POST | `/api/v1/analysis/preview` | Deterministic preview analysis of structured signals |

Missing prerequisites (for example generating before planning) return `409`; an unknown repository
profile returns `404`.

## Interactive Analysis Lab — `POST /api/v1/analysis/preview`

Deterministic, stateless preview analysis over **structured repository signals**. Powers the
`/analysis-lab` product route.

- **Authentication**: standard API key + `X-DeceptiForge-Org-Id`. Organization is resolved from the
  authenticated identity — a body `organization_id` is neither accepted nor trusted.
- **Permission**: `analysis:preview` (viewer, analyst, admin, owner). Sensor and unscoped service
  credentials are rejected (`403`).
- **Request** (`AnalysisPreviewRequest`): `{ signals: RepositorySignals, scenario_id?: string,
  options?: { include_alternatives?: bool, maximum_recommendations?: 1..20, minimum_confidence?:
  0..1 } }`. Options are a strict allowlist — no engine names, classes, or executable config.
- **RepositorySignals** (all optional, bounded): `languages, frameworks, package_managers, services,
  naming_patterns, infrastructure, databases, documentation, secret_locations, ai_surfaces`. Unknown
  top-level keys are reported back as `input_summary.ignored_fields`; unknown nested keys are
  dropped. Path-like strings are descriptive metadata only — the server never opens them.
- **Response** (`AnalysisPreviewResponse`, `schema_version: analysis-preview-v1`): `input_summary,
  context_profile, vocabulary, sensitive_zones, placement_recommendations, warnings, confidence,
  engine_versions, request_id, generated_at`. Each inferred value carries its confidence, supporting
  signals, and a deterministic explanation.
- **Deterministic**: identical input yields identical output (excluding `generated_at`). No GPT is
  called; no filesystem scan, repository clone, or code execution occurs.
- **Stateless**: input and results are never persisted. Only safe operational metadata is emitted
  (organization, actor, request id, scenario id, payload size, duration, outcome) — never the raw
  JSON input.
- **Limits**: request body over the transport limit → `413`; contract violation or too many
  aggregate representative paths → `422`; per-organization+actor rate limit exceeded → `429` with
  `Retry-After`.

Example request:

```json
{
  "signals": {
    "services": [{"name": "payment-service"}, {"name": "ledger-api"}],
    "databases": [{"engine": "PostgreSQL", "data_domain_terms": ["payment", "settlement"]}],
    "naming_patterns": {"domain_terms": ["payment", "settlement", "reconciliation"]},
    "secret_locations": [{"path": "services/payment/.env.example", "category": "payment_gateway"}]
  },
  "scenario_id": "fintech-payments"
}
```

## End-to-end flow

```text
scan ─► profile
         └─ plan ─► context + placement plan
                     └─ generate ─► decoy plan
                                     └─ evaluate ─► believability/safety reports
                                                     └─ monitoring/events ─► detection ─► alert ─► incident
```

`POST /monitoring/events` rebuilds the monitoring engine from the stored decoy plan and its accepted
validation reports, scans the submitted `value` for a decoy's trace identifier, and — on a hit —
persists a raw detection event, a normalized alert, and re-reconstructs incidents from that
organization's bounded recent alerts.

Surfaces for `/monitoring/events`: `file`, `repository`, `database`, `text`.

## Run locally

```sh
cp .env.example .env                 # set DATABASE_URL
docker compose up -d postgres        # from the repo root
cd apps/api
pip install -e '.[dev]'
alembic upgrade head                 # create the pipeline tables
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000/docs` for interactive OpenAPI.

### Example

```sh
curl -sX POST localhost:8000/repositories/scan \
  -H 'content-type: application/json' -d '{"path":"/path/to/repo","name":"payments"}'
# → {"repository_id":"...","profile":{...}}

curl -sX POST localhost:8000/placements/plan \
  -H 'content-type: application/json' -d '{"repository_id":"<id>"}'
curl -sX POST localhost:8000/decoys/generate \
  -H 'content-type: application/json' -d '{"repository_id":"<id>"}'
curl -sX POST localhost:8000/validation/evaluate \
  -H 'content-type: application/json' -d '{"decoy_plan_id":"<id>"}'
curl -sX POST localhost:8000/monitoring/events -H 'content-type: application/json' \
  -d '{"decoy_plan_id":"<id>","surface":"repository","location":"src/x.py","value":"copied <trace>"}'
curl -s localhost:8000/alerts
curl -s localhost:8000/incidents
```

## In-process demo (no server or PostgreSQL)

```sh
cd apps/api
python -m scripts.demo /path/to/repo
```

Runs the full pipeline against an in-memory SQLite database and prints the scan summary, decoy
counts, detection result, and the reconstructed incident.

## Demo mode and safety gating

- `DEMO_ENABLED` (default **false**) gates the `/demo/*` routes. They mount only when it is true —
  never through `APP_ENV` naming alone.
- `POST /repositories/scan` accepts a server-side path and is therefore restricted: it returns
  **403** unless `APP_ENV=development`. `DEMO_ENABLED` only exposes fixed-fixture demo routes;
  production must supply a repository id / integration handle instead of a raw path (future work).

## Notes and limits

- `POST /repositories/scan` reads a local path only in development (see gating above); a
  production deployment must constrain and authorize the scan source.
- Monitoring and alerting engines are stateful and are rebuilt per request from persisted artifacts;
  deduplication and tripwire state therefore live only within a single request.
- All routes require the organization/API-key boundary; production API keys must be bound through
  `API_KEY_BINDINGS`. The current identity layer is still a stub, not OAuth/RBAC.
