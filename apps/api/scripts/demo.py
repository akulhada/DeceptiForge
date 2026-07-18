# Purpose: run the whole deception pipeline in-process for a hackathon demo.
# Responsibilities: scan a repository, plan placements, generate and validate decoys, simulate an
#   agent touching a decoy, then print the resulting alert and reconstructed incident. It uses an
#   in-memory SQLite database so no PostgreSQL or running server is required.
# Usage: python -m scripts.demo [repository_path]
from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.base import Base
from app.models import records as _records  # noqa: F401  (register tables)
from app.repositories.artifacts import ArtifactRepository
from app.services.pipeline import PipelineService


def main() -> None:
    target = sys.argv[1] if len(sys.argv) > 1 else str(Path.cwd())
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    service = PipelineService(ArtifactRepository(session))

    repository_id, profile = service.scan(target, None)
    print(f"scanned {profile.repository_name}: {profile.file_count} files")

    _, _, plan = service.plan(repository_id)
    print(f"placements: {len(plan.recommendations)} recommended")

    decoy_plan_id, decoys = service.generate(repository_id)
    print(f"decoys: {len(decoys.assets)} generated")
    if not decoys.assets:
        print("no decoys admitted; pick a richer repository to demo")
        return

    reports = service.evaluate(decoy_plan_id)
    accepted = [report for report in reports if report.decision.value == "accept"]
    print(f"validation: {len(accepted)}/{len(reports)} accepted")

    trace = decoys.assets[0].trigger_metadata.trace_identifier
    event, alert = service.ingest_event(
        decoy_plan_id, "repository", "src/exfiltrated.py", f"copied {trace}"
    )
    print(f"detection: {'HIT' if event else 'miss'}; alert: {alert.title if alert else 'none'}")

    for incident in service.incidents():
        print(f"incident: {incident.incident_type.value} severity={incident.severity.value}")
        print(f"  hypothesis: {incident.root_cause_hypothesis}")


if __name__ == "__main__":
    main()
