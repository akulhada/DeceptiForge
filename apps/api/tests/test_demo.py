# Purpose: verify the demo-only endpoints that power the dashboard.
# Responsibilities: confirm seed builds a dataset, state aggregates it, and simulate produces an
#   alert and incident. Dependencies: the client fixture.
from __future__ import annotations


def test_seed_then_state_then_simulate(client) -> None:
    empty = client.get("/demo/state")
    assert empty.status_code == 200
    assert empty.json()["overview"]["total_decoys"] == 0

    seeded = client.post("/demo/seed")
    assert seeded.status_code == 200
    overview = seeded.json()["overview"]
    assert overview["total_decoys"] >= 1
    assert overview["accepted_decoys"] >= 1
    assert seeded.json()["profile"]["repository_name"] == "acme-payments"
    assert seeded.json()["placement_plan"]["recommendations"]

    simulated = client.post("/demo/simulate-detection")
    assert simulated.status_code == 200
    body = simulated.json()
    assert body["overview"]["monitor_events"] >= 1
    assert body["overview"]["alerts"] >= 1
    assert body["incidents"]
    assert body["incidents"][0]["timeline"]


def test_state_is_empty_before_seeding(client) -> None:
    body = client.get("/demo/state").json()
    assert body["profile"] is None
    assert body["decoy_plan"] is None
    assert body["overview"]["coverage"]["overall"] == 0
