# Capacity planning

Capacity recommendations are derived only from a passed `performance_runs` record. The current model
uses measured monitoring events-per-second-per-API replica and configured headroom; absent a passed
measurement it returns `uncertified`, rather than guessing.

Plan for API CPU <60%, workers <70%, database CPU/storage <65/70%, Redis memory <65%, and at least
2x the certified critical-ingestion burst. Record infrastructure topology with every performance run;
results from different topology are not comparable.
