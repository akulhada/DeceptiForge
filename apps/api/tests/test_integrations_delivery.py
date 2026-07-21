# Purpose: verify the outbox + delivery worker — signed webhook delivery, idempotent enqueue,
#   retry-then-deliver, dead-letter on permanent/exhausted failure, adapter payloads, and that two
#   workers never deliver the same row twice.
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config.settings import Settings
from app.database.base import Base
from app.models import records as _records  # noqa: F401
from app.models.domain.integrations import EventType
from app.models.domain.operations import Severity
from app.models.records import IntegrationDeadLetterRecord, IntegrationDeliveryRecord
from app.repositories.integrations import IntegrationRepository
from app.services.integrations import mapping, outbox
from app.services.integrations.adapter import HttpRequest, HttpResponse, TransportError
from app.services.integrations.adapters import WebhookAdapter, get_adapter
from app.services.integrations.worker import DeliveryWorker
from app.services.monitor_signing import body_sha256, sign

_NOW = datetime(2026, 7, 19, tzinfo=UTC)


def _settings(**over) -> Settings:  # type: ignore[no-untyped-def]
    base = dict(
        database_url="postgresql+psycopg://u:p@localhost/db",  # type: ignore[arg-type]
        app_env="development",
        security_export_max_attempts=3,
        security_export_allow_private_networks=True,
    )
    base.update(over)
    return Settings(**base)  # type: ignore[arg-type]


def _session() -> Session:
    e = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(e)
    return sessionmaker(bind=e, expire_on_commit=False)()


class RecordingTransport:
    def __init__(self, status: int = 200) -> None:
        self.status = status
        self.calls: list[HttpRequest] = []

    def send(self, request: HttpRequest, *, timeout: float) -> HttpResponse:
        self.calls.append(request)
        return HttpResponse(status=self.status, headers={})


class FlakyTransport:
    def __init__(self, statuses: list[int]) -> None:
        self.statuses = statuses
        self.i = 0

    def send(self, request: HttpRequest, *, timeout: float) -> HttpResponse:
        s = self.statuses[min(self.i, len(self.statuses) - 1)]
        self.i += 1
        if s == 0:
            raise TransportError("offline")
        return HttpResponse(status=s, headers={})


def _integration(repo: IntegrationRepository, org, itype="generic_webhook", endpoint=None):  # type: ignore[no-untyped-def]
    return repo.create_integration(
        organization_id=org,
        integration_type=itype,
        name="siem",
        endpoint=endpoint or "https://10.0.0.5/hook",
        secret="signing-secret",
        config_json="{}",
        routing_json="{}",
        payload_profile="standard",
        minimum_severity="low",
        include_narrative=False,
        include_coverage=True,
        include_operational=True,
        created_by_actor_id=None,
    )


def _event():  # type: ignore[no-untyped-def]
    return mapping.build_alert_event(
        event_type=EventType.ALERT_CREATED,
        org="org-1",
        occurred_at=_NOW,
        alert_id="a1",
        severity=Severity.HIGH,
        title="Alert",
        summary="decoy accessed",
        confidence=0.9,
        trace_ids=("DFAI-abc",),
    )


def test_secret_encrypted_and_not_returned() -> None:
    session = _session()
    repo = IntegrationRepository(session, _settings())
    integ = _integration(repo, uuid4())
    session.commit()
    assert "signing-secret" not in (integ.secret_ciphertext or "")
    assert repo.resolve_secret(integ) == "signing-secret"


def test_outbox_enqueue_is_idempotent() -> None:
    session = _session()
    settings = _settings()
    repo = IntegrationRepository(session, settings)
    org = uuid4()
    _integration(repo, org)
    session.commit()
    n1 = outbox.emit_event(repo, organization_id=org, envelope=_event(), settings=settings)
    n2 = outbox.emit_event(repo, organization_id=org, envelope=_event(), settings=settings)
    session.commit()
    assert n1 == 1 and n2 == 0  # duplicate source event -> no second delivery
    assert len(session.scalars(select(IntegrationDeliveryRecord)).all()) == 1


def test_worker_delivers_signed_webhook() -> None:
    session = _session()
    settings = _settings()
    repo = IntegrationRepository(session, settings)
    org = uuid4()
    _integration(repo, org)
    outbox.emit_event(repo, organization_id=org, envelope=_event(), settings=settings)
    session.commit()
    transport = RecordingTransport(200)
    DeliveryWorker(session, transport, settings).run_once(now=_NOW)
    session.commit()
    delivery = session.scalars(select(IntegrationDeliveryRecord)).one()
    assert delivery.status == "delivered"
    req = transport.calls[0]
    # Signature verifies over the canonical webhook string.
    canonical = "\n".join(
        (
            "df-webhook-v1",
            str(delivery.id),
            "deceptiforge.alert.created",
            req.headers["X-DeceptiForge-Timestamp"],
            body_sha256(req.body),
        )
    )
    assert req.headers["X-DeceptiForge-Signature"] == sign("signing-secret", canonical)
    assert b"signing-secret" not in req.body


def test_retry_then_deliver() -> None:
    session = _session()
    settings = _settings()
    repo = IntegrationRepository(session, settings)
    org = uuid4()
    _integration(repo, org)
    outbox.emit_event(repo, organization_id=org, envelope=_event(), settings=settings)
    session.commit()
    transport = FlakyTransport([503, 200])
    DeliveryWorker(session, transport, settings).run_once(now=_NOW)
    session.commit()
    d = session.scalars(select(IntegrationDeliveryRecord)).one()
    assert d.status == "retrying" and d.attempt_count == 1
    # Advance past next_attempt and run again -> delivered.
    future = _NOW + timedelta(hours=1)
    d.next_attempt_at = future - timedelta(minutes=1)
    session.flush()
    DeliveryWorker(session, transport, settings).run_once(now=future)
    session.commit()
    assert session.scalars(select(IntegrationDeliveryRecord)).one().status == "delivered"


def test_permanent_failure_dead_letters() -> None:
    session = _session()
    settings = _settings()
    repo = IntegrationRepository(session, settings)
    org = uuid4()
    _integration(repo, org)
    outbox.emit_event(repo, organization_id=org, envelope=_event(), settings=settings)
    session.commit()
    DeliveryWorker(session, RecordingTransport(401), settings).run_once(now=_NOW)
    session.commit()
    d = session.scalars(select(IntegrationDeliveryRecord)).one()
    assert d.status == "dead_lettered"
    assert len(session.scalars(select(IntegrationDeadLetterRecord)).all()) == 1


def test_ssrf_blocked_endpoint_dead_letters() -> None:
    session = _session()
    settings = _settings(security_export_allow_private_networks=False)
    repo = IntegrationRepository(session, settings)
    org = uuid4()
    # Endpoint validation is skipped at create in this unit; the worker revalidates and blocks it.
    _integration(repo, org, endpoint="https://127.0.0.1/hook")
    outbox.emit_event(repo, organization_id=org, envelope=_event(), settings=settings)
    session.commit()
    DeliveryWorker(session, RecordingTransport(200), settings).run_once(now=_NOW)
    session.commit()
    d = session.scalars(select(IntegrationDeliveryRecord)).one()
    assert d.status == "dead_lettered" and d.safe_error_code == "ssrf_blocked"


def test_two_workers_do_not_double_deliver() -> None:
    session = _session()
    settings = _settings()
    repo = IntegrationRepository(session, settings)
    org = uuid4()
    _integration(repo, org)
    outbox.emit_event(repo, organization_id=org, envelope=_event(), settings=settings)
    session.commit()
    # Worker A claims (lease). A second claim finds nothing to lease.
    a = repo.claim_deliveries(10, 60)
    b = repo.claim_deliveries(10, 60)
    assert len(a) == 1 and len(b) == 0


def test_adapters_build_expected_requests() -> None:
    from app.services.integrations.adapter import AdapterConfig

    env = _event()
    config = AdapterConfig(endpoint="https://siem/x", secret="tok", options={"index": "sec"})
    splunk = get_adapter("splunk_hec").build_request(env, config, delivery_id="d1")
    assert splunk.headers["Authorization"] == "Splunk tok"
    elastic = get_adapter("elastic").build_request(env, config, delivery_id="d1")
    assert elastic.method == "PUT" and elastic.url.endswith("/sec/_doc/d1")
    webhook = WebhookAdapter().build_request(env, config, delivery_id="d1")
    assert "X-DeceptiForge-Signature" in webhook.headers
