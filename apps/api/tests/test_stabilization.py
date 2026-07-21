# Purpose: verify the stabilization-sprint fixes.
# Responsibilities: persistent alert dedup across requests, monitoring payload limits, bounded and
#   non-over-grouping incident reconstruction, org-bound API keys, safe error responses, CORS
#   fail-closed, and artifact-size rejection. Dependencies: client/make_client and direct engines.
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config.constants import DEMO_ORGANIZATION_ID
from app.database.base import Base
from app.middleware.cors import configure_cors
from app.middleware.observability import RequestContextMiddleware, register_exception_handlers
from app.models import records as _records  # noqa: F401
from app.models.domain.intelligence import RepositoryIntelligenceProfile
from app.models.domain.operations import (
    AlertEvidence,
    DetectionMethod,
    DetectionSource,
    MonitorType,
    NormalizedAlert,
    RawDetectionEvent,
    Severity,
)
from app.repositories.artifacts import ArtifactRepository, ArtifactTooLargeError
from app.services.alerting import AlertingPipeline
from app.services.incident_reconstruction import IncidentConfig, IncidentReconstructionEngine

_KEY = "local-development-key"
_ORG_A = str(uuid4())
_ORG_B = str(uuid4())


# ---- finding 1: persistent dedup across requests -------------------------------------------------


def _seed_decoy(client) -> tuple[str, str]:
    state = client.post("/demo/seed").json()
    asset = state["decoy_plan"]["assets"][0]
    return state["decoy_plan_id"], asset["trigger_metadata"]["trace_identifier"]


def test_repeated_events_across_requests_update_one_alert(client) -> None:
    decoy_plan_id, trace = _seed_decoy(client)
    body = {
        "decoy_plan_id": decoy_plan_id,
        "surface": "repository",
        "location": "src/x.py",
        "value": f"copied {trace}",
    }
    first = client.post("/monitoring/events", json=body).json()["alert"]
    for _ in range(3):
        client.post("/monitoring/events", json=body)

    alerts = client.get("/alerts").json()["alerts"]
    assert len(alerts) == 1
    assert alerts[0]["event_count"] == 4
    assert alerts[0]["first_seen"] == first["first_seen"]


def _event(trace: str, monitor: MonitorType, location: str) -> RawDetectionEvent:
    return RawDetectionEvent(
        event_id=uuid4(),
        trace_identifier=trace,
        decoy_id=uuid4(),
        monitor_type=monitor,
        observed_location=location,
        observed_value_excerpt=f"prefix {trace}",
        timestamp=datetime.now(UTC),
        source=DetectionSource.REPOSITORY,
        confidence=1.0,
        severity_suggestion=Severity.HIGH,
        evidence_digest="a" * 64,
        detection_method=DetectionMethod.CONTENT_ACCESS,
        correlation_id=uuid4(),
    )


def test_thousand_duplicate_events_produce_one_alert() -> None:
    pipeline = AlertingPipeline()
    fixed_decoy = uuid4()
    for _ in range(1000):
        event = _event("DFG-DUP", MonitorType.REPOSITORY, "src/x.py").model_copy(
            update={"decoy_id": fixed_decoy}
        )
        pipeline.ingest(event, None)
    assert len(pipeline.alerts()) == 1
    assert pipeline.alerts()[0].event_count == 1000


def test_out_of_order_duplicate_preserves_alert_time_bounds() -> None:
    start = datetime.now(UTC)
    pipeline = AlertingPipeline()
    first = _event("DFG-ORDER", MonitorType.REPOSITORY, "src/x.py").model_copy(
        update={"timestamp": start + timedelta(seconds=30)}
    )
    duplicate = first.model_copy(update={"event_id": uuid4(), "timestamp": start})
    pipeline.ingest(first, None)
    updated = pipeline.ingest(duplicate, None)
    assert updated is not None
    assert updated.event_count == 2
    assert updated.first_seen == start
    assert updated.last_seen == start + timedelta(seconds=30)


# ---- finding 2: monitoring payload limit ---------------------------------------------------------


def test_oversized_monitoring_value_rejected_and_not_persisted(client) -> None:
    decoy_plan_id, _ = _seed_decoy(client)
    response = client.post(
        "/monitoring/events",
        json={
            "decoy_plan_id": decoy_plan_id,
            "surface": "repository",
            "location": "src/x.py",
            "value": "x" * 65_537,
        },
    )
    assert response.status_code == 413
    assert client.get("/alerts").json()["alerts"] == []


# ---- finding 3: reconstruction correctness / bounds ----------------------------------------------


def _alert(trace: str, monitor: MonitorType, at: datetime) -> NormalizedAlert:
    return NormalizedAlert(
        alert_id=uuid4(),
        trace_identifier=trace,
        decoy_id=uuid4(),
        severity=Severity.HIGH,
        title="trace",
        summary="observed",
        source_monitor=monitor,
        confidence=0.9,
        first_seen=at,
        last_seen=at,
        event_count=1,
        deduplication_key=f"{trace}:id:{monitor.value}:path:repository:content_access",
        affected_placement_id=uuid4(),
        affected_decoy_type="secret",
        evidence=(AlertEvidence(excerpt=trace, digest="a" * 64, location="src/x.py"),),
        raw_event_ids=(uuid4(),),
        recommended_actions=("review",),
        correlation_id=uuid4(),
    )


def test_unrelated_traces_same_monitor_stay_separate() -> None:
    now = datetime.now(UTC)
    incidents = IncidentReconstructionEngine().reconstruct(
        (_alert("DFG-1", MonitorType.REPOSITORY, now), _alert("DFG-2", MonitorType.REPOSITORY, now))
    )
    assert len(incidents) == 2


def test_same_trace_multiple_monitors_is_one_multi_surface_incident() -> None:
    now = datetime.now(UTC)
    a = _alert("DFG-X", MonitorType.REPOSITORY, now)
    b = _alert("DFG-X", MonitorType.TEXT_PAYLOAD, now + timedelta(seconds=5))
    incidents = IncidentReconstructionEngine().reconstruct((a, b))
    assert len(incidents) == 1
    assert len(incidents[0].affected_surfaces) == 2


def test_large_alert_set_is_bounded() -> None:
    now = datetime.now(UTC)
    alerts = tuple(
        _alert(f"DFG-{index}", MonitorType.REPOSITORY, now + timedelta(seconds=index))
        for index in range(2000)
    )
    incidents = IncidentReconstructionEngine().reconstruct(alerts, IncidentConfig(max_alerts=100))
    assert len(incidents) <= 100


# ---- finding 10: org-bound API keys --------------------------------------------------------------


def test_api_key_is_bound_to_one_organization(make_client) -> None:
    bindings = f'{{"key-a": "{_ORG_A}"}}'
    with make_client(
        demo_enabled=False, auth_enabled=True, app_env="production", api_key_bindings=bindings
    ) as client:
        ok = client.get(
            "/incidents",
            headers={"X-DeceptiForge-API-Key": "key-a", "X-DeceptiForge-Org-Id": _ORG_A},
        )
        assert ok.status_code == 200
        mismatch = client.get(
            "/incidents",
            headers={"X-DeceptiForge-API-Key": "key-a", "X-DeceptiForge-Org-Id": _ORG_B},
        )
        assert mismatch.status_code == 403
        assert client.get("/incidents").status_code == 401  # missing key


def test_auth_bypass_rejected_in_production(make_client) -> None:
    """A production deployment with authentication disabled must refuse to start.

    Previously this configuration booted and rejected every protected request with 401, which left a
    deployment that looked healthy while being operationally unusable. Startup validation now fails
    closed instead. Request-time enforcement remains as defense in depth.
    """
    import pytest

    with pytest.raises(RuntimeError, match="AUTH_ENABLED"):
        with make_client(auth_enabled=False, app_env="production"):
            pass


# ---- finding 7: safe error responses -------------------------------------------------------------


def test_unexpected_error_returns_safe_correlated_response() -> None:
    app = FastAPI()
    app.add_middleware(RequestContextMiddleware)
    register_exception_handlers(app)

    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError("leak /etc/passwd and secret token")

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/boom")
    assert response.status_code == 500
    assert response.json()["detail"] == "internal server error"
    assert response.json()["request_id"]
    assert "leak" not in response.text and "RuntimeError" not in response.text
    assert response.headers["x-request-id"]


# ---- finding 6: CORS fail-closed -----------------------------------------------------------------


def test_cors_rejects_wildcard_origin_with_credentials() -> None:
    with pytest.raises(ValueError):
        configure_cors(FastAPI(), ["*"], allow_credentials=True)


def test_cors_fails_closed_without_origins() -> None:
    app = FastAPI()
    configure_cors(app, [], allow_credentials=True)
    assert all("CORSMiddleware" not in str(mw.cls) for mw in app.user_middleware)


# ---- finding 9: artifact-size rejection ----------------------------------------------------------


def test_oversized_artifact_rejected_before_persistence() -> None:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    repo = ArtifactRepository(session, max_artifact_bytes=10)
    profile = RepositoryIntelligenceProfile(
        repository_name="payments", root_path="/repo", is_git_repository=True, file_count=1
    )
    with pytest.raises(ArtifactTooLargeError):
        repo.add_repository(DEMO_ORGANIZATION_ID, "payments", "/repo", profile)
