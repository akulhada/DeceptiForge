# Purpose: prove the AI tripwire lifecycle against the in-memory fake RAG/MCP adapters.
# Responsibilities: connector secrets encrypted; execute deploys + verifies + activates monitoring
#   only after verification; idempotent retry deploys one asset; retire deletes only the owned
#   asset; a modified external asset causes drift_detected; cross-org access rejected; events are
#   minimized (never persist prompts/chunks/outputs); classification/severity are deterministic.
from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config.settings import Settings
from app.database.base import Base
from app.models import records as _records  # noqa: F401
from app.models.domain.ai_tripwire import (
    AiEventType,
    AiTripwireStatus,
    MinimizedAiEvent,
    SurfaceType,
)
from app.models.domain.operations import Severity
from app.repositories.ai_tripwire import (
    AiTripwireRepository,
    ConnectorNotFoundError,
    DeploymentNotFoundError,
)
from app.services.ai_tripwire.classification import (
    AiExposureType,
    classify,
    severity,
)
from app.services.ai_tripwire.connectors import FakeMcpAdapter, FakeRagAdapter
from app.services.ai_tripwire.minimize import minimize_metadata
from app.services.ai_tripwire.preview import build_mcp_preview, build_rag_preview
from app.services.ai_tripwire.service import AiTripwireService


def _settings() -> Settings:
    return Settings(
        database_url="postgresql+psycopg://u:p@localhost/db",  # type: ignore[arg-type]
        app_env="development",
        ai_tripwire_allowed_collections=["deceptiforge_decoys"],
    )


def _engine() -> Engine:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    return engine


class _Ctx:
    def __init__(self, surface: SurfaceType = SurfaceType.RAG_DOCUMENT) -> None:
        self.settings = _settings()
        self.session: Session = sessionmaker(bind=_engine(), expire_on_commit=False)()
        self.repo = AiTripwireRepository(self.session, self.settings)
        self.rag = FakeRagAdapter()
        self.mcp = FakeMcpAdapter()
        self.rag.register_collection("deceptiforge_decoys")
        self.org = uuid4()
        self.surface = surface
        self.trace = "DFAI-abc123"
        if surface == SurfaceType.RAG_DOCUMENT:
            self.connector = self.repo.create_rag_connector(
                organization_id=self.org,
                connector_type="pgvector",
                name="store",
                secret="s3cr3t-token",
                index_or_collection="deceptiforge_decoys",
                namespace=None,
                created_by_actor_id=uuid4(),
            )
            preview, _ = build_rag_preview(
                deployment_id=str(uuid4()),
                connector_id=str(self.connector.id),
                target_collection="deceptiforge_decoys",
                decoy_kind="architecture_note",
                trace_token=self.trace,
                expires_at=None,
                settings=self.settings,
            )
        else:
            self.connector = self.repo.create_mcp_connector(
                organization_id=self.org,
                name="mcp",
                server_reference="stg.internal",
                transport_type="stdio",
                secret="s3cr3t-token",
                created_by_actor_id=uuid4(),
            )
            preview, _ = build_mcp_preview(
                deployment_id=str(uuid4()),
                connector_id=str(self.connector.id),
                target_collection="deceptiforge_decoys",
                decoy_kind="mcp_resource",
                trace_token=self.trace,
                surface=SurfaceType.MCP_RESOURCE,
                expires_at=None,
                settings=self.settings,
            )
        self.record = self.repo.create_deployment(
            organization_id=self.org,
            surface_type=surface.value,
            connector_id=self.connector.id,
            target_collection="deceptiforge_decoys",
            decoy_kind=preview.decoy_kind,
            trace_id=self.trace,
            requested_by_actor_id=uuid4(),
            expires_at=None,
        )
        self.repo.set_preview(self.record, preview)
        self.svc = AiTripwireService(self.repo, self.rag, self.mcp, self.settings)

    def to_deploying(self) -> None:
        for target in (
            AiTripwireStatus.AWAITING_APPROVAL,
            AiTripwireStatus.APPROVED,
            AiTripwireStatus.DEPLOYING,
        ):
            self.repo.transition(self.record, target)


def test_connector_secret_is_encrypted() -> None:
    c = _Ctx()
    assert "s3cr3t-token" not in c.connector.secret_ciphertext
    assert c.repo.resolve_secret(c.connector.secret_ciphertext) == "s3cr3t-token"


def test_execute_deploys_verifies_and_activates_rag() -> None:
    c = _Ctx()
    c.to_deploying()
    c.svc.execute(c.org, c.record.id)
    c.session.commit()
    assert c.record.status == AiTripwireStatus.DEPLOYED.value
    assert c.record.monitoring_activated_at is not None
    assert c.record.external_asset_id is not None
    assert c.rag.asset_count("deceptiforge_decoys") == 1


def test_execute_deploys_verifies_and_activates_mcp() -> None:
    c = _Ctx(SurfaceType.MCP_RESOURCE)
    c.to_deploying()
    c.svc.execute(c.org, c.record.id)
    c.session.commit()
    assert c.record.status == AiTripwireStatus.DEPLOYED.value
    assert c.record.monitoring_activated_at is not None
    assert c.mcp.resource_count() == 1


def test_monitoring_not_activated_before_verification() -> None:
    # A deploy whose external asset cannot be verified must not activate monitoring.
    c = _Ctx()
    c.to_deploying()
    original = c.rag.verify_document

    def _fail_verify(*a, **k):  # type: ignore[no-untyped-def]
        from app.services.ai_tripwire.connectors import VerifyResult

        return VerifyResult(False, False, False)

    c.rag.verify_document = _fail_verify  # type: ignore[method-assign]
    c.svc.execute(c.org, c.record.id)
    c.session.commit()
    c.rag.verify_document = original  # type: ignore[method-assign]
    assert c.record.status == AiTripwireStatus.VERIFICATION_FAILED.value
    assert c.record.monitoring_activated_at is None


def test_execute_is_idempotent() -> None:
    c = _Ctx()
    c.to_deploying()
    c.svc.execute(c.org, c.record.id)
    assert c.rag.asset_count("deceptiforge_decoys") == 1
    # Duplicate job queued before the first completed: force back to deploying, re-run.
    c.record.status = AiTripwireStatus.DEPLOYING.value
    c.session.flush()
    c.svc.execute(c.org, c.record.id)
    c.session.commit()
    assert c.rag.asset_count("deceptiforge_decoys") == 1  # still one asset


def test_retire_deletes_only_owned_asset() -> None:
    c = _Ctx()
    c.to_deploying()
    c.svc.execute(c.org, c.record.id)
    # A foreign asset in the same collection must survive retirement.
    c.rag._collections["deceptiforge_decoys"]["rag:deceptiforge_decoys:foreign"] = (
        c.rag._collections["deceptiforge_decoys"][c.record.external_asset_id]
    )
    assert c.rag.asset_count("deceptiforge_decoys") == 2
    c.repo.transition(c.record, AiTripwireStatus.RETIRING)
    c.svc.retire(c.org, c.record.id)
    c.session.commit()
    assert c.record.status == AiTripwireStatus.RETIRED.value
    assert c.rag.asset_count("deceptiforge_decoys") == 1  # foreign asset untouched


def test_modified_external_asset_causes_drift() -> None:
    c = _Ctx()
    c.to_deploying()
    c.svc.execute(c.org, c.record.id)
    c.rag.mutate("deceptiforge_decoys", c.record.external_asset_id, "tampered-hash")
    c.repo.transition(c.record, AiTripwireStatus.RETIRING)
    c.svc.retire(c.org, c.record.id)
    c.session.commit()
    assert c.record.status == AiTripwireStatus.DRIFT_DETECTED.value
    assert c.rag.asset_count("deceptiforge_decoys") == 1  # not deleted


def test_cross_org_access_rejected() -> None:
    c = _Ctx()
    other = uuid4()
    try:
        c.repo.get_deployment(other, c.record.id)
        raise AssertionError("expected DeploymentNotFoundError")
    except DeploymentNotFoundError:
        pass
    try:
        c.repo.get_rag_connector(other, c.connector.id)
        raise AssertionError("expected ConnectorNotFoundError")
    except ConnectorNotFoundError:
        pass


def test_events_are_minimized_no_raw_content() -> None:
    c = _Ctx()
    c.to_deploying()
    c.svc.execute(c.org, c.record.id)
    event = MinimizedAiEvent(
        deployment_id=str(c.record.id),
        trace_id=c.trace,
        surface_type=SurfaceType.RAG_DOCUMENT,
        event_type=AiEventType.DOCUMENT_RETRIEVED,
        source_id="agent-7",
        monitor_identity="signed-monitor-1",
        confidence=0.9,
        # Ingestion minimizes before the event is ever constructed/persisted.
        minimized_metadata=minimize_metadata(
            {
                "collection": "deceptiforge_decoys",
                "prompt": "SECRET USER PROMPT",  # forbidden -> dropped
                "output": "SECRET ANSWER",  # forbidden -> dropped
            }
        ),
        observed_at=datetime.now(UTC),
    )
    stored = c.repo.add_event(c.org, event)
    c.session.commit()
    assert "SECRET USER PROMPT" not in stored.minimized_metadata
    assert "SECRET ANSWER" not in stored.minimized_metadata
    assert "prompt" not in stored.minimized_metadata
    assert "collection" in stored.minimized_metadata


def test_classification_is_deterministic() -> None:
    rag = frozenset({AiEventType.DOCUMENT_RETRIEVED})
    assert classify(rag) == AiExposureType.RAG_RETRIEVAL_EXPOSURE
    assert classify(rag) == AiExposureType.RAG_RETRIEVAL_EXPOSURE
    answer = frozenset({AiEventType.DOCUMENT_RETRIEVED, AiEventType.TRACE_IN_ANSWER})
    assert classify(answer) == AiExposureType.RAG_ANSWER_LEAK
    multi = frozenset({AiEventType.DOCUMENT_RETRIEVED, AiEventType.RESOURCE_READ})
    assert classify(multi) == AiExposureType.MULTI_SURFACE_AI_EXPOSURE


def test_severity_is_deterministic_and_bumps() -> None:
    base = severity(
        AiExposureType.RAG_RETRIEVAL_EXPOSURE,
        event_count=1,
        distinct_sources=1,
        surface_count=1,
    )
    bumped = severity(
        AiExposureType.RAG_RETRIEVAL_EXPOSURE,
        event_count=5,
        distinct_sources=3,
        surface_count=2,
    )
    assert base == Severity.MEDIUM
    assert _ordinal(bumped) > _ordinal(base)
    # Deterministic: same inputs, same output.
    assert bumped == severity(
        AiExposureType.RAG_RETRIEVAL_EXPOSURE,
        event_count=5,
        distinct_sources=3,
        surface_count=2,
    )


def _ordinal(sev: Severity) -> int:
    order = (Severity.INFO, Severity.LOW, Severity.MEDIUM, Severity.HIGH, Severity.CRITICAL)
    return order.index(sev)
