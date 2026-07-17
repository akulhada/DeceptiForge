<!-- Purpose: define deterministic normalization of raw monitoring detections. -->

# Alerting Pipeline

The Alerting Pipeline consumes `RawDetectionEvent` records from Monitoring Instrumentation and produces immutable `NormalizedAlert` records. It does not scan payloads, activate monitors, generate decoys, or reconstruct incidents.

Raw events require a trace, short excerpt, and confidence of at least `.5`. Enrichment uses tripwire metadata when available and falls back to event-only metadata otherwise. Severity is deterministic: confidence contributes 35 points, monitor type contributes 10–25, decoy type 10–20, placement priority 15, and repeated activity up to 10. Thresholds are critical ≥90, high ≥70, medium ≥45, low ≥25, otherwise info.

Deduplication keys combine trace, decoy, monitor, location, source, and detection method. Matching events inside the default 15-minute window update count, timestamps, severity, evidence, and raw event references; a different location creates a separate alert. Evidence retains only the capped monitoring excerpt, event digest, location, timestamps, and IDs. Recommendations are selected deterministically by monitor type. Future dashboards consume normalized alerts, while a future incident engine can use their correlation IDs and raw-event references.
