# Backpressure

Monitoring admission rejects a tenant that exceeds its short burst, sustained event, or pending
reconstruction-job budget with `429` and `Retry-After`. Redis unavailability fails closed when Redis
is the configured backend. This is intentional: accepting an event that cannot safely retain its
security processing would hide overload.

P0 ingestion remains isolated from P1 reconstruction. P2/P3 exports, retention, coverage, analytics,
and report work must remain on their dedicated worker paths and must not consume ingestion capacity.
