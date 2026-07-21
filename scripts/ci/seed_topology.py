# Purpose: seed the minimum tenant state a production-shaped CI boot needs to drive one real signed
#   event through to an alert and an incident.
# Responsibilities: create an organization, an ingest-scoped API key, a monitor signing credential,
#   and a deterministic decoy plan (from the bundled fictional fixture), then print the identifiers
#   as shell-consumable key=value lines. Uses the ordinary service layer — no development-only demo
#   route, no GPT, and no arbitrary path: the fixture ships with the image.
# Run inside the API image with DATABASE_URL set. Output is written to stdout; the monitor secret is
# printed because CI must sign with it, so treat CI logs for this job as sensitive.
from __future__ import annotations

import sys
from pathlib import Path
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config.settings import get_settings
from app.services.decoy_generation import DecoyGenerationConfig
from app.repositories.artifacts import ArtifactRepository
from app.services.api_keys import ApiKeyService
from app.services.monitor_credentials import MonitorCredentialService
from app.services.pipeline import PipelineService

def _fixture_dir() -> Path:
    """Locate the bundled fictional repository in a source checkout or inside the API image."""
    here = Path(__file__).resolve()
    candidates = [
        here.parents[2] / "apps" / "api" / "app" / "demo" / "acme-payments",  # source checkout
        Path("/app/app/demo/acme-payments"),  # API image layout
    ]
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    raise SystemExit("bundled demo fixture not found")


def main() -> int:
    settings = get_settings()
    engine = create_engine(str(settings.database_url))
    session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()

    organization_id = uuid4()
    repository = ArtifactRepository(session)
    pipeline = PipelineService(repository, organization_id)

    # Deterministic pipeline over the bundled fictional repository: scan -> plan -> generate.
    repository_id, _ = pipeline.scan(str(_fixture_dir()), "acme-payments")
    pipeline.plan(repository_id)
    decoy_plan_id, plan = pipeline.generate(
        repository_id, DecoyGenerationConfig(namespace=f"ci:{repository_id}")
    )
    pipeline.evaluate(decoy_plan_id)

    trace = plan.assets[0].trigger_metadata.trace_identifier

    # Least privilege, two purposes: the ingest key carries monitoring:ingest only (service role),
    # while verification uses a separate read-only key. Neither is widened to suit the other.
    keys = ApiKeyService(session)
    _, api_key = keys.create(organization_id, "ci-ingest", "service")
    _, read_api_key = keys.create(organization_id, "ci-read", "analyst")
    monitor, monitor_secret = MonitorCredentialService(session, settings).create(
        organization_id, "ci-topology"
    )
    session.commit()

    for line in (
        f"ORG_ID={organization_id}",
        f"API_KEY={api_key}",
        f"READ_API_KEY={read_api_key}",
        f"MONITOR_ID={monitor.monitor_id}",
        f"MONITOR_SECRET={monitor_secret}",
        f"DECOY_PLAN_ID={decoy_plan_id}",
        f"TRACE={trace}",
    ):
        print(line)
    session.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
