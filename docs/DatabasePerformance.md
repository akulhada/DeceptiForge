# Database performance

High-frequency alert upserts use a uniqueness constraint and row locking. Reconstruction queries use
organization and correlation keys, and worker claims use bounded batches. New tenant-limit and
performance-run tables have organization/status indexes.

Before certification, capture `EXPLAIN (ANALYZE, BUFFERS)` for ingestion, alert upsert, related-alert
lookup, queue claim, audit pagination, and retention deletes. Use keyset pagination for new large list
endpoints; do not add time/hash partitioning until measurements justify its migration and retention
cost.
