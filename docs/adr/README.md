<!-- Purpose: index of Architecture Decision Records for long-lived DeceptiForge boundaries. -->

# Architecture Decision Records

Per [Architecture.md](../Architecture.md) ("Decision log"), decisions that change a long-lived
boundary are recorded here **before** implementation. Each ADR is immutable once `Accepted`; revisit
by adding a new ADR that supersedes it (note the supersession in both).

Format: Context → Decision → Consequences → Status. Keep them short and concrete.

| ADR | Title | Status |
| --- | --- | --- |
| [0001](0001-request-time-auth-enforcement.md) | Request-time auth enforcement over startup rejection | Accepted |
| [0002](0002-fake-adapter-boundary.md) | Fake-adapter boundary for external side effects | Accepted |
| [0003](0003-production-feature-flag-policy.md) | Production feature-flag policy (default-off) | Accepted |
| [0004](0004-retention-and-evidence-handling.md) | Retention and evidence-at-rest handling | Accepted |
| [0005](0005-release-certification-criteria.md) | Release certification criteria (strict verification) | Accepted |

New ADR: copy the shape of an existing one, take the next number, add a row above.
