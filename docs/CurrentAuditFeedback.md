# Current Audit Feedback

**Scope:** CI workflows, production settings guards, production Compose, CORS, dashboard headers,
and current GitHub Actions status.

**Audited tree:** `feat/deployment-modes` at `4253bee`.

## Result

No verified code or CI deployment blocker was found in the audited tree.

The latest pull-request CI run for this commit passed all jobs, including backend quality,
PostgreSQL and Redis integration, frontend checks, production configuration, production topology,
Docker, supply-chain, secret scanning, and reliability scripts.

## Verified controls

- Production Compose pins Postgres and Redis by digest and provides health checks before dependent
  services start. See `docker-compose.prod.example.yml`.
- Production-like modes reject disabled authentication, fail-open Redis behavior, missing shared
  replay protection, and unsafe demonstration-surface configuration. See
  `apps/api/app/config/settings.py`.
- Judge mode remains hardened; it permits only explicitly enabled judge/demo surfaces and does not
  permit local filesystem scanning or the Analysis Lab.
- CORS permits dashboard methods (`GET`, `POST`, `PUT`, `DELETE`) and only headers sent by browser
  dashboard clients. Signed-monitor headers remain intentionally unavailable to page CORS because
  signed ingestion is performed by trusted server-side senders or the extension.
- Dashboard security headers and nonce-based CSP are emitted by the web app and exercised against
  built HTTP responses in CI.
- Python dependencies use hash-verified lockfiles. SBOM generation uses a pinned CycloneDX package.
- CI boots the production-shaped Compose topology, performs migrations as a release step, starts
  workers, sends a real signed monitoring event, and verifies alert and incident creation.

## Findings

### High: documentation no longer matches deployment-mode behavior

`docs/ProductionBoundary.md` states that `/demo/*` mounts only in `development` and cannot appear
on a production-like deployment. The current settings deliberately permit the curated demo in the
hardened `judge` environment when `DEMO_ENABLED=true`.

Update the document before release so deployment operators understand the supported judge-mode
exception and do not treat it as a production tenant surface.

### Medium: standalone worker runtime validation needs explicit coverage

The API validates production settings during application construction. Standalone worker processes
should either invoke equivalent runtime validation or have a documented and tested worker-specific
validation profile. The current CI topology confirms the present configuration works, but does not
prove all future worker deployment changes will fail fast.

### Low: CI runs are not cancelled when superseded

The workflow does not currently define a pull-request `concurrency` group. Adding one with
`cancel-in-progress: true` would reduce duplicate CI work without changing test coverage.

## Release evidence still required outside CI

- Clean-clone deployment in judge/staging infrastructure.
- Ingress/CDN verification that CSP and other security headers survive unchanged.
- TLS, edge request-body limits, and edge CORS verification.
- Encrypted backup restore drill in isolated infrastructure.
- Judge credential/session provisioning and teardown runbook exercise.

