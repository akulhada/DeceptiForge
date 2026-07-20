<!-- Purpose: Elastic integration notes. -->

# Elastic integration

Delivers each canonical event as a document to an Elastic index / data stream.

## Configuration

- **endpoint**: the Elasticsearch base URL (e.g. `https://es.example.com:9243`). SSRF-validated;
  https required outside development.
- **secret**: an API key, stored encrypted and sent as `Authorization: ApiKey <key>` — never logged.
- **options**: `index` (default `deceptiforge-security`).

## Deterministic document id

The adapter issues `PUT {endpoint}/{index}/_doc/{delivery_id}`. Using the delivery id as the document
id means a duplicate delivery is an **idempotent overwrite**, not a duplicate document — combined
with the outbox idempotency key, one logical event yields exactly one document.

## Payload

The minimized `SecurityEventEnvelope` as the document body. Response classification and
retry/dead-letter follow the shared rules. Bulk batching can be added behind the same adapter when
safe.
