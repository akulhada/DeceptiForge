# ADR 0002 — Fake-adapter boundary for external side effects

**Status:** Accepted

## Context

DeceptiForge integrates with external systems that cause real, sometimes irreversible side effects:
GitHub (pull requests / deployed decoys), database honey-record targets, RAG/MCP vector stores and
servers, and SIEM/SOAR destinations. Building and testing against live third-party tenants is
unsafe (real PRs, real vendor data) and non-deterministic in CI.

## Decision

Every external side-effect integration is expressed behind an adapter interface with two
implementations: a **concrete** provider client (production wiring) and a **fake** adapter
(deterministic, in-memory, contacts nothing). CI and the default configuration use the fakes. The
live GitHub App path is, at present, a fake adapter only — provider integrations remain future work.
Docs and status reports must state plainly which surfaces are real software vs fake adapters.

## Consequences

- CI exercises adapter contracts, SSRF validation, concurrency, and idempotency against fakes — no
  paid vector store, MCP server, SIEM tenant, or real repository is contacted.
- "Implemented" never silently means "wired to a live provider." Readiness and status docs must
  distinguish the two (see [ProductionReadiness.md](../ProductionReadiness.md)).
- Promoting a fake to a concrete client is a boundary change: it needs a threat model, least-privilege
  credentials, and a docs/status update — and should reference this ADR.
