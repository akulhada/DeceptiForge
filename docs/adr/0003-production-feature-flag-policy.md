# ADR 0003 — Production feature-flag policy (default-off)

**Status:** Accepted

## Context

The platform has many capability surfaces added across milestones: decoy deployment, database honey
records, RAG/MCP tripwires, browser and agent sensors, measured coverage, SIEM export, and
multi-region reliability. Each carries its own risk (external side effects, new ingestion paths,
new credentials). Enabling all of them by default would make the safe configuration the exception.

## Decision

Every capability surface is gated behind its own environment feature flag and is **off by default**
(e.g. `DECOY_DEPLOYMENT_ENABLED`, `DATABASE_HONEY_DEPLOYMENT_ENABLED`, `RAG_CONNECTORS_ENABLED`,
`MCP_CONNECTORS_ENABLED`, `BROWSER_SENSOR_ENABLED`, `AGENT_SENSOR_ENABLED`, `COVERAGE_ENGINE_ENABLED`,
`SECURITY_INTEGRATIONS_ENABLED`, `CAPACITY_MANAGEMENT_ENABLED`). A router is included only when its
flag is set; module import must not depend on a flag being on. Production startup validation
(`validate_runtime`) rejects unsafe combinations (e.g. app-level rate limiting without Redis).

## Consequences

- The default deployment is the minimal, safest one; enabling a surface is a deliberate, auditable act.
- Enabling a surface in staging/production requires exercising its verification steps
  (see [StagingVerification.md](../checklists/StagingVerification.md)) — an enabled-but-unverified
  surface is a no-go.
- Import-time side effects must stay flag-independent (a router import pulling a runtime dependency
  such as `httpx` must therefore declare it as a runtime dependency, not dev-only).
- New surfaces follow the same pattern: new flag, default off, own verification steps.
