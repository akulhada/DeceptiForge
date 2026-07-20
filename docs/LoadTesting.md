# Load testing

All tests use deterministic synthetic data and must target isolated staging only. Tenant profiles:
small (10 repositories/100 decoys), medium (100/5,000), large (1,000/100,000). Treat them as test
profiles, not promises.

Run steady ingestion, a 10x burst, replay/signature rejection traffic, concurrent deduplication,
reconstruction backlog, dashboard reads during bursts, and large/small tenant contention. Record the
revision, topology, dataset seed, duration, throughput, latency percentiles, error rate, queue depth,
and bottleneck. Never send real evidence or credentials through a load harness.
