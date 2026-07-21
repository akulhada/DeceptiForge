# ADR 0006 — Reject unusable configuration at startup

**Status:** Accepted — supersedes [ADR 0001](0001-request-time-auth-enforcement.md)

## Context

ADR 0001 chose request-time enforcement and explicitly declined a startup guard for
`AUTH_ENABLED=false`, on the grounds that per-request rejection is the surface that matters. That
reasoning is still correct as far as it goes: a booted process cannot serve an unauthenticated
protected request either way.

What it missed is the operational failure mode. A deployment with `AUTH_ENABLED=false` boots,
reports itself healthy, passes readiness, and then rejects every protected request with `401`. It is
running and completely unusable, and nothing in the platform says so. The same shape applies to
`REDIS_FAIL_MODE=open`, where replay protection and rate limiting silently degrade during an
outage, and to demonstration-surface flags set in an environment that forbids them, where the
configuration claims a surface exists and the router does not mount it.

ADR 0001 anticipated this: it recorded that superseding the decision would require updating the
bypass-rejection tests and would itself be ADR-worthy.

## Decision

Refuse to start when the configuration is unusable or unsafe outside development. `validate_runtime`
now rejects `AUTH_ENABLED=false`, `REDIS_FAIL_MODE=open`, `MONITOR_SIGNATURE_REQUIRED=false`, and
any demonstration-surface flag the deployment mode forbids.

Request-time enforcement is **kept, not replaced**. The startup guard is an operator signal; the
per-request check remains the security boundary, so a future configuration path that bypasses
startup validation cannot serve unauthenticated traffic.

## Consequences

- An operator gets an immediate, explicit failure naming the offending variable, instead of a
  healthy-looking deployment that answers `401` to everything.
- The tests ADR 0001 protected were updated rather than deleted: they now assert the startup
  rejection, which is the stronger claim. Tests that still need a deliberately misconfigured app
  construct `Settings` directly and call the request path without `validate_runtime`.
- A stray flag in a tenant deployment is a boot failure rather than a silent behaviour difference.
  This trades availability for correctness deliberately: the deployment was already broken, and
  failing loudly is how the operator learns.
- Production settings helpers must pin these flags explicitly, because pydantic-settings reads
  `.env` and a developer's local value would otherwise leak into a production assertion.
