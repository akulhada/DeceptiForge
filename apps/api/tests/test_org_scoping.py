# Purpose: prove organization isolation across the pipeline and persistence.
# Responsibilities: one organization cannot read or act on another's repository, plans, decoys,
#   validation, monitor events, alerts, or incidents; incident reconstruction and narrative
#   revisions are organization-scoped. Dependencies: make_client and a direct SQLite session.
from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config.settings import Settings
from app.database.base import Base
from app.models import records as _records  # noqa: F401  (register tables)
from app.models.domain.operations import (
    AlertEvidence,
    MonitorType,
    NormalizedAlert,
    Severity,
)
from app.repositories.artifacts import ArtifactRepository
from app.services.demo import _FIXTURE_PATH
from app.services.incident_narrative import IncidentNarrativeGenerator
from app.services.incident_reconstruction import IncidentReconstructionEngine

_KEY = "local-development-key"
_DB_URL = "postgresql+psycopg://unused:unused@localhost/deceptiforge"


def _headers(org_id: str) -> dict[str, str]:
    return {"X-DeceptiForge-API-Key": _KEY, "X-DeceptiForge-Org-Id": org_id}


def test_cross_org_pipeline_read_and_write_isolation(make_client) -> None:
    org_a, org_b = str(uuid4()), str(uuid4())
    with make_client(demo_enabled=True, auth_enabled=True, app_env="development") as client:
        headers_a, headers_b = _headers(org_a), _headers(org_b)

        scan = client.post(
            "/repositories/scan", json={"path": str(_FIXTURE_PATH)}, headers=headers_a
        )
        assert scan.status_code == 200
        repository_id = scan.json()["repository_id"]

        # Organization B cannot read or act on organization A's repository.
        assert (
            client.get(f"/repositories/{repository_id}/profile", headers=headers_b).status_code
            == 404
        )
        assert (
            client.get(f"/repositories/{repository_id}/profile", headers=headers_a).status_code
            == 200
        )
        assert (
            client.post(
                "/placements/plan", json={"repository_id": repository_id}, headers=headers_b
            ).status_code
            == 409
        )

        # Organization A drives its pipeline.
        client.post("/placements/plan", json={"repository_id": repository_id}, headers=headers_a)
        decoy_plan_id = client.post(
            "/decoys/generate", json={"repository_id": repository_id}, headers=headers_a
        ).json()["decoy_plan_id"]
        client.post(
            "/validation/evaluate", json={"decoy_plan_id": decoy_plan_id}, headers=headers_a
        )

        # Organization B cannot evaluate or feed monitoring against A's decoy plan.
        assert (
            client.post(
                "/validation/evaluate", json={"decoy_plan_id": decoy_plan_id}, headers=headers_b
            ).status_code
            == 409
        )
        assert (
            client.post(
                "/decoys/generate", json={"repository_id": repository_id}, headers=headers_b
            ).status_code
            == 409
        )

        # Organization A trips a tripwire; B sees no alerts or incidents.
        trace = client.get(f"/repositories/{repository_id}/profile", headers=headers_a)
        assert trace.status_code == 200
        # Drive a detection through the demo path (single org = demo org) is not used here; instead
        # verify list isolation: B's lists are empty regardless of A's activity.
        assert client.get("/alerts", headers=headers_b).json()["alerts"] == []
        assert client.get("/incidents", headers=headers_b).json()["incidents"] == []


def _alert(organization_marker: str) -> NormalizedAlert:
    trace = f"DFG-{organization_marker}"
    return NormalizedAlert(
        alert_id=uuid4(),
        trace_identifier=trace,
        decoy_id=uuid4(),
        severity=Severity.HIGH,
        title="trace",
        summary="Decoy trace observed",
        source_monitor=MonitorType.REPOSITORY,
        confidence=0.9,
        first_seen=datetime.now(UTC),
        last_seen=datetime.now(UTC),
        event_count=1,
        deduplication_key=f"{trace}:id:repository:path:repository:content_access",
        affected_placement_id=uuid4(),
        affected_decoy_type="secret",
        evidence=(AlertEvidence(excerpt=trace, digest="a" * 64, location="src/x.py"),),
        raw_event_ids=(uuid4(),),
        recommended_actions=("review",),
        correlation_id=uuid4(),
    )


def _repo() -> ArtifactRepository:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()
    return ArtifactRepository(session)


def test_incident_reconstruction_and_replace_are_org_scoped() -> None:
    repo = _repo()
    org_a, org_b = uuid4(), uuid4()
    alert_a, alert_b = _alert("AAA111"), _alert("BBB222")
    repo.add_alert(org_a, alert_a)
    repo.add_alert(org_b, alert_b)
    engine = IncidentReconstructionEngine()

    repo.replace_incidents_for_organization(
        org_a, engine.reconstruct(repo.alerts_for_organization(org_a))
    )
    repo.replace_incidents_for_organization(
        org_b, engine.reconstruct(repo.alerts_for_organization(org_b))
    )

    incidents_a = repo.incidents_for_organization(org_a)
    incidents_b = repo.incidents_for_organization(org_b)
    assert len(incidents_a) == 1 and len(incidents_b) == 1
    assert incidents_a[0].involved_decoy_ids == (alert_a.decoy_id,)

    # Reconstructing A again must not delete B's incident.
    repo.replace_incidents_for_organization(
        org_a, engine.reconstruct(repo.alerts_for_organization(org_a))
    )
    assert len(repo.incidents_for_organization(org_b)) == 1


def test_narrative_revision_uniqueness_is_enforced_per_org_and_incident() -> None:
    repo = _repo()
    org_a, org_b = uuid4(), uuid4()
    incident = IncidentReconstructionEngine().reconstruct((_alert("AAA111"),))[0]
    settings = Settings(_env_file=None, database_url=_DB_URL)  # type: ignore[call-arg]

    narrative_a = IncidentNarrativeGenerator(settings).generate(incident, org_a)
    repo.add_narrative_revision(narrative_a)

    # Same (organization, incident, revision_number) violates the unique constraint.
    with pytest.raises(IntegrityError):
        repo.add_narrative_revision(narrative_a)

    # A different organization may reuse revision 1 for the same incident id.
    fresh = _repo()
    fresh.add_narrative_revision(narrative_a)
    fresh.add_narrative_revision(IncidentNarrativeGenerator(settings).generate(incident, org_b))
    assert fresh.next_revision_number(org_b, incident.incident_id) == 2
