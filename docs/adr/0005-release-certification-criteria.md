# ADR 0005 — Release certification criteria (strict verification)

**Status:** Accepted

## Context

Staging verification scripts previously could report success while silently skipping or softening the
most important checks: the smoke test accepted a missing-plan `409` as a "valid ingest", and
`verify_runtime.sh` emitted `PASS` even when Docker/worker topology, database/Redis readiness,
cross-org isolation, signed-ingestion controls, and log redaction were skipped. The result was
false confidence — a green result that certified nothing.

## Decision

Release certification requires **positively observed** checks, not absent-therefore-skipped ones.

- **Smoke test** (`scripts/staging/smoke_test.sh`): the valid signed-ingest path MUST return `200`
  (signature accepted AND seeded decoy plan matched). A `409` (plan not seeded) or any non-200 fails
  the smoke test — it must not pass on the same code that also signals replay rejection.
- **Runtime verification** (`scripts/staging/verify_runtime.sh`) has two modes via `VERIFY_MODE`:
  - `strict` (default, for certification): every skipped/softened check that masks a real assertion
    becomes a hard FAIL — missing Docker/worker topology, unreachable DB/Redis, non-org-bound key,
    absent signed-ingestion env, and un-attested log redaction (`LOG_REDACTION_ATTESTED=yes`) all fail.
  - `diagnostic`: partial local checks allowed; a PASS explicitly does **not** certify a release.
- **Evidence** ([StagingVerification.md](../checklists/StagingVerification.md)): a result is "pass"
  only if actually observed; results are never prefilled. "Staging verified" cannot be claimed without
  a completed record (green release commit, migration, health/readiness, multi-worker, retention,
  log redaction, go/no-go).

## Consequences

- A default `verify_runtime.sh` run on a laptop without Docker now FAILS (as it should for
  certification); use `VERIFY_MODE=diagnostic` for partial local runs.
- CI does not invoke these scripts; they run against a live staging deployment by an operator.
- No completed staging verification record exists yet, so no release is certified. Producing one
  requires a real staging run — it must not be fabricated.
- Weakening any of these gates is a boundary change and should reference this ADR.
