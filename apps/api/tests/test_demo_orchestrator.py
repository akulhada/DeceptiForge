# Purpose: verify the one-click demo orchestrator, coverage, reset, and export.
# Responsibilities: prove a run completes every step, coverage is computed, reset clears state, the
#   run is retrievable/exportable, and demo routes stay gated. Dependencies: client/make_client.
from __future__ import annotations

from uuid import uuid4


def test_run_completes_every_step_with_coverage(client) -> None:
    run = client.post("/demo/run")
    assert run.status_code == 200
    body = run.json()

    assert body["status"] == "complete"
    assert [step["status"] for step in body["steps"]] == ["complete"] * len(body["steps"])
    assert {step["key"] for step in body["steps"]} >= {
        "repository_analyzed",
        "decoys_validated",
        "incident_reconstructed",
        "ai_summary",
        "coverage_calculated",
    }
    assert body["coverage"]["overall"] > 0.9
    assert body["narrative"] is not None
    assert body["state"]["incidents"]


def test_reset_clears_all_state(client) -> None:
    client.post("/demo/run")
    reset = client.post("/demo/reset").json()
    assert reset["profile"] is None
    assert reset["overview"]["total_decoys"] == 0


def test_run_is_retrievable_and_exportable(client) -> None:
    run_id = client.post("/demo/run").json()["run_id"]

    assert client.get(f"/demo/run/{run_id}").status_code == 200
    assert client.get(f"/demo/run/{uuid4()}").status_code == 404

    markdown = client.get(f"/demo/run/{run_id}/export", params={"format": "markdown"})
    assert markdown.status_code == 200
    assert "## Coverage" in markdown.text
    assert "## Incident" in markdown.text


def test_demo_run_is_gated_by_demo_enabled(make_client) -> None:
    with make_client(demo_enabled=False, app_env="production") as client:
        assert client.post("/demo/run").status_code == 404
