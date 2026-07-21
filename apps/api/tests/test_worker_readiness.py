# Purpose: operational readiness must reflect whether the system can actually reconstruct incidents,
#   while remaining distinct from HTTP instance readiness — a stalled worker must not deregister
#   every API replica from the load balancer.
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.models.records import ReconstructionJobRecord


def _client(make_client):  # type: ignore[no-untyped-def]
    return make_client(demo_enabled=False, auth_enabled=True, app_env="development")


def _job(client, *, status: str, age_seconds: float = 0, processed: bool = False) -> None:  # type: ignore[no-untyped-def]
    created = datetime.now(UTC) - timedelta(seconds=age_seconds)
    session = client.app_session()
    session.add(
        ReconstructionJobRecord(
            organization_id=uuid4(),
            status=status,
            trace_identifier="trace",
            decoy_id=uuid4(),
            window_start=created,
            window_end=created,
            created_at=created,
            processed_at=datetime.now(UTC) if processed else None,
        )
    )
    session.commit()
    session.close()


# ---- healthy baselines ---------------------------------------------------------------------------


def test_no_work_is_healthy_not_stalled(make_client) -> None:  # type: ignore[no-untyped-def]
    """A fresh deployment has never run a job; absence of work is not a dead worker."""
    with _client(make_client) as client:
        body = client.get("/ready/operational").json()
        assert body["workers"]["status"] == "ok"
        assert body["workers"]["queue_depth"] == 0


def test_recent_pending_work_is_healthy(make_client) -> None:  # type: ignore[no-untyped-def]
    with _client(make_client) as client:
        _job(client, status="pending", age_seconds=5)
        body = client.get("/ready/operational").json()
        assert body["workers"]["status"] == "ok"
        assert body["workers"]["queue_depth"] == 1


# ---- the signals the audit asked for ---------------------------------------------------------


def test_reports_every_required_worker_signal(make_client) -> None:  # type: ignore[no-untyped-def]
    with _client(make_client) as client:
        _job(client, status="done", processed=True)
        _job(client, status="pending", age_seconds=30)
        workers = client.get("/ready/operational").json()["workers"]
        for field in (
            "queue_depth",
            "queue_age_seconds",
            "reconstruction_lag_seconds",
            "failed_job_count",
            "last_successful_job_at",
            "heartbeat_age_seconds",
            "stuck_claimed_jobs",
        ):
            assert field in workers, field
        assert workers["last_successful_job_at"] is not None
        # Liveness is derived, not a dedicated heartbeat channel; that is stated, not implied.
        assert workers["heartbeat_source"] == "derived_from_last_completed_job"


# ---- stall detection -------------------------------------------------------------------------


def test_old_queue_marks_workers_stalled(make_client) -> None:  # type: ignore[no-untyped-def]
    with _client(make_client) as client:
        _job(client, status="pending", age_seconds=100_000)
        response = client.get("/ready/operational")
        assert response.status_code == 503
        workers = response.json()["workers"]
        assert workers["status"] == "stalled"
        assert "queue_age_exceeded" in workers["reasons"]
        assert workers["reconstruction_lag_seconds"] > 900


def test_claimed_job_that_never_completes_is_detected(make_client) -> None:  # type: ignore[no-untyped-def]
    """A worker that died mid-flight leaves a claimed job behind."""
    with _client(make_client) as client:
        _job(client, status="claimed", age_seconds=100_000)
        _job(client, status="pending", age_seconds=100_000)
        workers = client.get("/ready/operational").json()["workers"]
        assert workers["stuck_claimed_jobs"] == 1
        assert workers["status"] == "stalled"


# ---- the separation the audit required -------------------------------------------------------


def test_stalled_worker_does_not_make_the_http_instance_unready(make_client) -> None:  # type: ignore[no-untyped-def]
    """Taking one worker down must not remove every API replica from service."""
    with _client(make_client) as client:
        _job(client, status="pending", age_seconds=100_000)

        instance = client.get("/ready")
        operational = client.get("/ready/operational")

        # The HTTP instance can still serve reads.
        assert instance.status_code == 200
        assert instance.json()["status"] == "ok"
        # Operational readiness is the surface that degrades.
        assert operational.status_code == 503
        assert operational.json()["status"] == "degraded"


def test_instance_readiness_still_surfaces_worker_state_for_visibility(make_client) -> None:  # type: ignore[no-untyped-def]
    with _client(make_client) as client:
        _job(client, status="pending", age_seconds=100_000)
        body = client.get("/ready").json()
        # Present for operators, but it does not change the gating decision.
        assert body["workers"]["status"] == "stalled"
        assert body["status"] == "ok"


def test_readiness_exposes_no_tenant_identifiers(make_client) -> None:  # type: ignore[no-untyped-def]
    """Probes are unauthenticated: aggregate counts only, never organization detail."""
    with _client(make_client) as client:
        organization_id = uuid4()
        session = client.app_session()
        session.add(
            ReconstructionJobRecord(
                organization_id=organization_id,
                status="pending",
                trace_identifier="secret-trace",
                decoy_id=uuid4(),
                window_start=datetime.now(UTC),
                window_end=datetime.now(UTC),
            )
        )
        session.commit()
        session.close()
        body = client.get("/ready/operational").text
        assert str(organization_id) not in body
        assert "secret-trace" not in body
