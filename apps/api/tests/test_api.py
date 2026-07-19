# Purpose: verify the API vertical slice end to end over an in-memory database.
# Responsibilities: exercise the create/read flow from scan through incidents and confirm missing
#   prerequisites surface as HTTP errors. Dependencies: the client fixture.
from __future__ import annotations

from pathlib import Path
from uuid import uuid4


def _seed_repository(tmp_path: Path) -> None:
    """Write a repository realistic enough to clear the decoy generator's admission bar."""
    (tmp_path / ".env.example").write_text(
        "PAYMENT_SERVICE_KEY=example\nPAYMENT_DB_HOST=localhost\n"
        "AUTH_JWT_SECRET=example\nAWS_REGION=us-east-1\nSTRIPE_API_KEY=example\n",
        encoding="utf-8",
    )
    (tmp_path / "Dockerfile").write_text("FROM python:3.12\n", encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text('[tool.poetry]\nname = "payments"\n', encoding="utf-8")
    (tmp_path / "poetry.lock").write_text("", encoding="utf-8")
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "architecture.md").write_text("# Architecture\nPostgreSQL and AWS.\n", encoding="utf-8")
    (docs / "runbook.md").write_text("# Runbook\n", encoding="utf-8")
    src = tmp_path / "src"
    src.mkdir()
    for name in ("payment-service", "billing-service", "invoice-worker"):
        (src / f"{name}.py").write_text(
            "import fastapi\nimport psycopg\n"
            "router.get('/v1/customer-profiles')\nDATABASE_URL = 'postgresql://x'\n",
            encoding="utf-8",
        )
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "ci.yml").write_text("name: ci\n", encoding="utf-8")


def test_full_pipeline_scan_to_incident(client, tmp_path) -> None:
    _seed_repository(tmp_path)

    scan = client.post("/repositories/scan", json={"path": str(tmp_path), "name": "payments"})
    assert scan.status_code == 200
    repository_id = scan.json()["repository_id"]

    profile = client.get(f"/repositories/{repository_id}/profile")
    assert profile.status_code == 200
    assert profile.json()["file_count"] >= 2

    plan = client.post("/placements/plan", json={"repository_id": repository_id})
    assert plan.status_code == 200
    assert plan.json()["plan"]["recommendations"]

    generate = client.post("/decoys/generate", json={"repository_id": repository_id})
    assert generate.status_code == 200
    decoy_plan_id = generate.json()["decoy_plan_id"]
    assets = generate.json()["plan"]["assets"]
    assert assets
    trace = assets[0]["trigger_metadata"]["trace_identifier"]

    evaluate = client.post("/validation/evaluate", json={"decoy_plan_id": decoy_plan_id})
    assert evaluate.status_code == 200
    assert evaluate.json()["reports"]

    event = client.post(
        "/monitoring/events",
        json={
            "decoy_plan_id": decoy_plan_id,
            "surface": "repository",
            "location": "src/leaked.py",
            "value": f"copied secret {trace} into new file",
        },
    )
    assert event.status_code == 200
    assert event.json()["detected"] is True

    alerts = client.get("/alerts")
    assert alerts.status_code == 200
    assert alerts.json()["alerts"]

    # Reconstruction is asynchronous: ingestion enqueues work, a worker builds the incidents.
    _drain_reconstruction(client)

    incidents = client.get("/incidents")
    assert incidents.status_code == 200
    assert incidents.json()["incidents"]


def _drain_reconstruction(client) -> None:  # type: ignore[no-untyped-def]
    from app.repositories.artifacts import ArtifactRepository
    from app.services.incident_reconstruction import ReconstructionWorker

    session = client.app_session()
    ReconstructionWorker(ArtifactRepository(session)).drain()
    session.commit()
    session.close()


def test_missing_profile_returns_404(client) -> None:
    response = client.get(f"/repositories/{uuid4()}/profile")
    assert response.status_code == 404


def test_generate_before_plan_returns_409(client, tmp_path) -> None:
    _seed_repository(tmp_path)
    repository_id = client.post("/repositories/scan", json={"path": str(tmp_path)}).json()[
        "repository_id"
    ]

    response = client.post("/decoys/generate", json={"repository_id": repository_id})
    assert response.status_code == 409


def test_monitoring_without_match_reports_no_detection(client, tmp_path) -> None:
    _seed_repository(tmp_path)
    repository_id = client.post("/repositories/scan", json={"path": str(tmp_path)}).json()[
        "repository_id"
    ]
    client.post("/placements/plan", json={"repository_id": repository_id})
    decoy_plan_id = client.post("/decoys/generate", json={"repository_id": repository_id}).json()[
        "decoy_plan_id"
    ]
    client.post("/validation/evaluate", json={"decoy_plan_id": decoy_plan_id})

    response = client.post(
        "/monitoring/events",
        json={
            "decoy_plan_id": decoy_plan_id,
            "surface": "text",
            "location": "clipboard",
            "value": "nothing sensitive here",
        },
    )
    assert response.status_code == 200
    assert response.json()["detected"] is False
