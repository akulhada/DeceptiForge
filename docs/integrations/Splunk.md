<!-- Purpose: Splunk HTTP Event Collector (HEC) integration notes. -->

# Splunk HEC integration

Delivers each canonical event to a Splunk HEC endpoint.

## Configuration

- **endpoint**: the HEC collector URL (e.g. `https://splunk.example.com:8088/services/collector`).
  SSRF-validated; https required outside development.
- **secret**: the HEC token, stored encrypted and sent as `Authorization: Splunk <token>` — never
  logged.
- **options**: `source`, `sourcetype` (default `deceptiforge:security`), `index`.

## Payload

```json
{
  "event": { "...": "minimized SecurityEventEnvelope" },
  "source": "deceptiforge",
  "sourcetype": "deceptiforge:security",
  "index": "main",
  "fields": { "deceptiforge_delivery_id": "<delivery id>" }
}
```

The delivery id is included for deduplication. Responses are classified with the shared rules:
2xx success; 408/429/5xx retry; other 4xx (bad token/forbidden/malformed) permanent. Bounded batch
size via `SECURITY_EXPORT_MAX_BATCH_SIZE`.

## Limitations

Acknowledgment (indexer ack) mode is not implemented in the first release; add it behind the same
adapter without changing the contract.
