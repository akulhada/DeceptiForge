<!-- Purpose: document the measured deception coverage engine — surfaces, controls, snapshots,
trends, the scheduled job, and why decoy count is not coverage. -->

# Coverage engine

The coverage engine measures **real** deception coverage across every deception/monitoring surface,
replacing demo estimates. It is deterministic, explainable, time-aware, organization-scoped, and
honest about unknown areas. GPT never contributes to scoring.

Disabled by default (`COVERAGE_ENGINE_ENABLED`); explicit staging/production enablement required.

## Surfaces

A unified inventory (`app/services/coverage_engine/inventory.py`) is built organization-scoped from
existing records across six surface types: `repository`, `database`, `rag`, `mcp`, `browser_ai`,
`ai_agent`. Each surface is scored deterministically (criticality/exposure/sensitivity/attack →
risk weight) with an explanation and an inventory confidence.

## Controls and dimensions

Each surface carries the controls actually present, mapped to nine dimensions: placement, sensor,
health, alerting, incident, lifecycle, identity, cross-surface, verification. Control status is read
from live deployment + sensor state (`active`/`degraded`/`expired`/`failed`). A failed or expired
control earns **no** credit. Alerting/incident/identity capabilities apply only where a live sensor
exists (a detection must be possible before it can become an alert or incident).

## Why decoy count is not coverage

Coverage is effectiveness- and risk-weighted, never a count. Effectiveness
(`scoring.control_effectiveness`) depends on status, believability, and verification freshness — not
quantity. Placement requires an **active decoy**; a sensor with no decoy is not placement coverage.
Many weak decoys in one low-value location cannot outweigh one strong, verified decoy on a critical
surface. See [CoverageMethodology](CoverageMethodology.md).

## Measured vs inferred, and unknown

Confidence reflects freshness and whether data is measured or inferred; a high score with low
confidence is shown as qualified, never as certainty. Surfaces with low inventory confidence are
marked **unknown** and reported separately — unknown weight is never counted as covered. A
near-perfect score with meaningful unknown weight or low confidence is flagged as misleading in the
dashboard.

## Snapshots and trends

Each calculation is persisted as an **immutable** `CoverageSnapshot` (with a `source_state_hash` and
`methodology_version`). History is never recomputed from mutable current state, so trends are
faithful. Persistence is idempotent by `source_state_hash` + methodology version, so concurrent or
scheduled runs that observe unchanged state create no new snapshot.

## Scheduled calculation

`python -m app.jobs.coverage` runs organization-scoped, advisory-locked (one snapshot under
concurrent invocation), bounded, and retryable. Authorized users can trigger a manual recalculation
(`POST /coverage/recalculate`, scope `coverage:recalculate`).

## API + permissions

`GET /coverage` (honest `no_snapshot` empty state), `/coverage/snapshots[/{id}]`,
`/coverage/surfaces`, `/coverage/gaps`, `/coverage/recommendations`, `/coverage/methodology`,
`/coverage/policy`, `POST /coverage/recalculate`. Scopes: `coverage:read`, `coverage:recalculate`,
`coverage:manage_policy`. See [PlacementOptimization](PlacementOptimization.md) for gaps +
recommendations.

## Limitations

Criticality inputs are deterministic defaults adjusted by name patterns; unusual layouts may need an
explicit coverage policy. The engine measures the surfaces DeceptiForge integrates with — surfaces
outside those integrations are not (and are not claimed to be) covered.
