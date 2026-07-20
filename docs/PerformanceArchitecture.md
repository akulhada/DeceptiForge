# Performance architecture

DeceptiForge keeps signed monitoring ingestion synchronous only through authentication, signature
verification, replay reservation, strict validation, quota admission, event persistence, and atomic
alert upsert. Incident reconstruction is queued; narratives, exports, coverage, and deployments stay
off the ingest path.

`CAPACITY_MANAGEMENT_ENABLED=true` adds organization-scoped monitoring admission and reconstruction
queue backpressure. Limits use Redis in production-like environments. Rejected requests return 429
with `Retry-After`; accepted durable events are never silently discarded.

Reconstruction workers claim a fair share per organization per batch. This protects a small tenant
from a large tenant's queue backlog. Other existing worker queues retain their current bounded claim
behavior and are not represented as fair-scheduled until they are wired to this contract.
