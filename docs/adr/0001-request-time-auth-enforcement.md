# ADR 0001 — Request-time auth enforcement over startup rejection

**Status:** Accepted

## Context

Production must never serve unauthenticated tenant traffic. One option is a startup guard: refuse to
boot when `AUTH_ENABLED=false` in a production environment. During hardening we found this guard
both weaker than it looks and in conflict with existing tests: several cases intentionally build a
production app with `auth_enabled=False` to prove that requests are still rejected
(`test_auth_bypass_rejected_in_production`).

## Decision

Enforce authentication at **request time**, not (only) at startup. In production, protected routes
reject unauthenticated/misauthenticated requests with `401`/`403` regardless of the `AUTH_ENABLED`
flag. We do **not** add a startup guard that fails the process on `AUTH_ENABLED=false`.

## Consequences

- The security guarantee holds per request, which is the surface that actually matters — a booted
  process cannot serve an unauthenticated protected request.
- Tests can construct deliberately misconfigured apps to assert the request-time rejection, without a
  startup guard masking the behavior.
- Operators do not get a boot-time failure signal for `AUTH_ENABLED=false`; readiness/verification
  and the request-time `401` are the signals instead. Accepted as the lesser risk.
- Superseding this (adding a startup guard) would require updating the bypass-rejection tests and is
  itself an ADR-worthy change.
