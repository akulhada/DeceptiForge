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


def test_reseeding_starts_a_new_demo_story(client) -> None:
    client.post("/demo/seed")
    client.post("/demo/simulate-detection")

    reseeded = client.post("/demo/seed")

    assert reseeded.status_code == 200
    assert reseeded.json()["overview"]["monitor_events"] == 0
    assert reseeded.json()["overview"]["alerts"] == 0
    assert reseeded.json()["overview"]["incidents"] == 0


def test_demo_state_scopes_artifacts_to_current_generation(client) -> None:
    client.post("/demo/seed")
    client.post("/demo/simulate-detection")
    client.post("/demo/seed")  # new generation; prior alert/incident remain in the database
    client.post("/demo/simulate-detection")

    overview = client.get("/demo/state").json()["overview"]

    # Global storage now holds two alerts/incidents; scoped state exposes only the current one.
    assert overview["alerts"] == 1
    assert overview["monitor_events"] == 1
    assert overview["incidents"] == 1
