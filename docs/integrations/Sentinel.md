<!-- Purpose: Microsoft Sentinel / Log Analytics integration notes. -->

# Microsoft Sentinel integration

Delivers each canonical event to a Sentinel-compatible ingestion endpoint.

## Configuration

- **endpoint**: a supported ingestion URL (a Logic App HTTP trigger, or a Data Collector /
  ingestion endpoint). SSRF-validated; https required outside development.
- **secret**: the shared key / bearer token, stored encrypted and sent as `Authorization: Bearer
  <token>` — never logged. Tenant secrets are never hardcoded.
- **options**: `log_type` (default `DeceptiForgeSecurity`).

## Transport abstraction

The adapter posts a signed JSON envelope. The transport is intentionally abstract so the concrete
Log Analytics Data Collector signature (or a newer ingestion API) can be swapped in later without
changing the `SecurityExportAdapter` contract or the canonical event.

## Payload

The minimized `SecurityEventEnvelope` as the JSON body, with `Log-Type` and a delivery id header for
correlation. Response classification and retry/dead-letter follow the shared rules.
