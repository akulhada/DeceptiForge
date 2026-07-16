<!-- Purpose: define contribution expectations. Responsibilities: protect architectural boundaries, quality, and secret handling. Future modules: add review ownership and release procedures when a team workflow exists. -->

# Contributing

## Before coding

Propose changes that introduce data collection, AI integrations, browser permissions, authentication, third-party services, or durable schema changes. Explain the threat model, ownership boundary, and rollback path.

## Change discipline

- Deliver features as small vertical slices; do not pre-create speculative abstractions.
- Keep database models, API schemas, and UI state independent.
- Add a migration with every persistent schema change.
- Do not commit `.env` files, keys, tokens, or production data.
- Keep extension permissions and host access at the minimum required scope.

## Verification

Run the relevant format, lint, typecheck, and test commands before review. Update documentation whenever a command, environment variable, architecture boundary, or setup step changes.
