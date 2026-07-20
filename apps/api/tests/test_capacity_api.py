"""Tenant-scoped capacity API and safe reconstruction queue backpressure."""

from app.config.constants import DEMO_ORGANIZATION_ID

_LIMITS = {
    "tier": "small",
    "monitoring_events_per_second": 20,
    "monitoring_burst": 50,
    "max_pending_jobs": 1,
    "max_concurrent_scans": 1,
    "max_concurrent_deployments": 1,
    "max_report_jobs": 1,
}


def test_tenant_limits_are_scoped_and_platform_capacity_is_not_tenant_visible(client) -> None:
    assert client.get("/limits").status_code == 200
    response = client.put(f"/admin/organizations/{DEMO_ORGANIZATION_ID}/limits", json=_LIMITS)
    assert response.status_code == 200
    assert client.get("/usage").json()["tier"] == "small"
    assert client.get("/admin/capacity/status").status_code == 403


def test_pending_reconstruction_quota_returns_retryable_backpressure(make_client) -> None:
    with make_client(capacity_management_enabled=True) as client:
        response = client.put(
            f"/admin/organizations/{DEMO_ORGANIZATION_ID}/limits", json=_LIMITS
        )
        assert response.status_code == 200
        state = client.post("/demo/seed").json()
        asset = state["decoy_plan"]["assets"][0]
        body = {
            "decoy_plan_id": state["decoy_plan_id"],
            "surface": "repository",
            "location": "src/x.py",
            "value": f"copied {asset['trigger_metadata']['trace_identifier']}",
        }
        assert client.post("/monitoring/events", json=body).status_code == 200
        response = client.post("/monitoring/events", json=body)

    assert response.status_code == 429
    assert response.headers["retry-after"] == "60"
