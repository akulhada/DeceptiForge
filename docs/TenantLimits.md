# Tenant limits

Each organization has one versioned policy: tier, monitoring events per second/burst, pending
reconstruction jobs, scan/deployment concurrency, and report jobs. Defaults are conservative and
come from settings; an organization owner can update only its own limits through
`PUT /admin/organizations/{organization_id}/limits`. Changes are audited.

`GET /usage` and `GET /limits` are tenant scoped. A limit is evaluated after monitoring signature and
replay checks but before any durable event is accepted. Retry with a fresh signed request after a 429.
