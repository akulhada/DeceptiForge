<!-- Purpose: document blind-spot detection and risk-based placement recommendations. -->

# Placement optimization

From each surface's coverage and controls, the engine derives explainable blind spots and ranks the
next best placements. Deterministic; GPT never scores.

## Blind-spot detection

`app/services/coverage_engine/blindspots.py` derives gaps with severity (from criticality) and an
expected coverage gain:

- `no_decoy` / `no_honey_records` / `no_rag_tripwire` / `no_mcp_tripwire` / `shadow_ai_no_policy` /
  `agent_no_scope_policy` — no active decoy on the surface.
- `decoy_no_sensor` — a decoy exists but no active sensor can detect interaction.
- `sensor_unhealthy` / `monitoring_activation_failed` — degraded or failed detection.
- `expired_not_replaced` — a decoy expired and was not replaced.
- `fragile_single_control` — a high-value surface relies on a single control (no defense in depth).
- `no_cross_surface` — activity cannot be correlated across surfaces.

Each gap lists the affected surface, why it matters, severity, missing controls, and expected gain.

## Recommendation scoring

`recommend.py` turns gaps into ranked recommendations. Each has an expected coverage gain, expected
detection gain, deployment risk, false-positive risk, implementation effort, confidence, and a
deterministic priority:

```
priority = risk_weight × (0.6×coverage_gain + 0.4×detection_gain)
           × (1 − 0.4×deployment_risk − 0.2×effort)
```

Higher-risk, higher-gap, higher-detection surfaces rank first; risk and effort penalize. Output is
bounded (`COVERAGE_MAX_RECOMMENDATIONS`).

## Safety constraints (filtered out)

Recommendations are **not** produced for: high deployment risk with low expected benefit; risk beyond
the organization's tolerance (`recommendation_risk_tolerance`); zero expected gain; or a duplicate
action on the same surface (no incremental gain). The engine respects organization policy, deployment
limits, protected paths/tables/collections, expiry policy, and approval requirements — it never
recommends unsafe or redundant placements.

## Accept is draft-only

Accepting a recommendation (`POST /coverage/recommendations/{id}/accept`) records intent only and
returns `auto_deployed: false`. It never deploys automatically — the operator still creates and
approves a deployment through the normal separation-of-duties flow.
