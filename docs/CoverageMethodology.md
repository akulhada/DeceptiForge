<!-- Purpose: document the deterministic coverage formula, weights, confidence, and unknown
handling. -->

# Coverage methodology (`coverage-v1`)

Coverage is a versioned, deterministic function of observed controls. Bump `METHODOLOGY_VERSION`
whenever the formula, weights, or dimension set change; the version is recorded on every snapshot and
folded into the `source_state_hash`, so snapshots are only comparable within a version.

## Dimension weights

`app/services/coverage_engine/formula.py::DIMENSION_WEIGHTS` (sum to 1.0):

| dimension | weight |
|---|---|
| placement | 0.22 |
| sensor | 0.20 |
| health | 0.16 |
| alerting | 0.10 |
| incident | 0.08 |
| lifecycle | 0.08 |
| identity | 0.06 |
| verification | 0.06 |
| cross_surface | 0.04 |

## Formula

Per surface: each dimension score is the best **active** control's effectiveness in that dimension
(0 if none). `surface_coverage = clamp(Σ dimension_score × dimension_weight + diversity_bonus)`. The
diversity bonus is small, bounded (≤0.10), and applies only once real placement exists — it can
never turn a zero-placement surface into a covered one.

Risk weighting: `risk_weight = criticality × (0.5 + 0.5 × coverage_requirement)`;
`weighted_coverage = surface_coverage × risk_weight` (0 for unknown surfaces).

Overall: `overall_score = Σ weighted_coverage(known) / Σ risk_weight(known)`. Unknown surfaces
contribute their risk weight to `unknown_weight`, reported separately — **never** counted as
covered. Division by zero yields 0 (honest empty state).

## Control effectiveness (quantity-agnostic)

`effectiveness = clamp(0.5 + 0.3×believability + 0.2×verification_freshness + ≤0.1×detections) ×
status_ceiling`. Status ceilings: active 1.0, degraded 0.5, inactive/expired/failed 0.0. Stale
verification decays freshness. Quantity is never summed into a surface score — one strong verified
control beats many stale ones.

## Confidence

`inventory_confidence` = measured (0.9) vs inferred (0.5), scaled by freshness and metadata
completeness. `aggregate_confidence` lowers as unknown ratio grows. A high score with low confidence
is surfaced as qualified in the dashboard, never as measured certainty.

## Unknown handling

A surface with inventory confidence below the floor (0.4) is `is_unknown`: excluded from both
numerator and denominator of the overall score and added to `unknown_weight`. This keeps the headline
score honest — we never inflate coverage by treating unmeasured surfaces as covered.

## Gaming resistance

Deploying many low-value decoys does not raise the score (effectiveness- and risk-weighted, not
counted). Marking surfaces unknown cannot hide risk (unknown is reported and lowers confidence).
Snapshots are immutable, so history cannot be rewritten from current state. GPT cannot influence any
score.
