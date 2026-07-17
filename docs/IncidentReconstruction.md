<!-- Purpose: define deterministic alert grouping before any GPT narrative layer. -->

# Incident Reconstruction

Incident Reconstruction consumes normalized alerts only. It neither scans payloads nor creates alerts. Alerts are conservatively grouped inside a configurable one-hour window when they share a trace, decoy, placement, correlation ID, or source/monitor relationship. Timelines are sorted by timestamp then alert ID and retain only existing alert excerpts, hashes, locations, and identifiers.

Types are determined by monitor mix: text payload is `ai_paste_leak`, repository is `repository_exposure`, database payload is `database_export`, file content is `file_copy_or_sync`, and multiple monitor surfaces are `multi_surface_exposure`. Incident severity starts with the highest alert severity and escalates for three or more alerts and cross-surface propagation. Hypotheses and actions are fixed mappings from incident type.

The GPT context bundle is structured data only: type, minimized timeline, hypothesis, and recommended actions. A later narrative generator may consume it but cannot replace correlation, evidence, or severity decisions. Complexity is O(A²) in the small in-memory MVP alert set; a future persistence adapter should pre-index trace, decoy, placement, correlation ID, and timestamp.
