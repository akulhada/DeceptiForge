# Purpose: orchestrate the AI tripwire lifecycle (deploy/verify/activate/retire) for RAG and MCP.
# Responsibilities: regenerate the exact inert asset deterministically, deploy through the connector
#   idempotently, verify the external asset + trace, activate monitoring only after verification,
#   and retire by deleting only the owned asset after a content-hash ownership check (drift blocks).
#   Org-scoped, audited; never logs secrets or raw content. Dependencies: repository, connectors,
#   content, settings.
from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from app.config.settings import Settings
from app.models.domain.ai_tripwire import (
    AiTripwireStatus,
    GeneratedMcpResource,
    GeneratedRagDocument,
    SurfaceType,
)
from app.repositories.ai_tripwire import AiTripwireRepository
from app.services.ai_tripwire.connectors import (
    ConnectorError,
    ConnSpec,
    McpConnectorAdapter,
    RagConnectorAdapter,
)
from app.services.ai_tripwire.content import generate_mcp_resource, generate_rag_document
from app.services.metrics import emit


class AiTripwireService:
    def __init__(
        self,
        repo: AiTripwireRepository,
        rag_client: RagConnectorAdapter,
        mcp_client: McpConnectorAdapter,
        settings: Settings,
        *,
        request_id: str = "worker",
    ) -> None:
        self._repo = repo
        self._rag = rag_client
        self._mcp = mcp_client
        self._settings = settings
        self._request_id = request_id

    def _audit(self, org: UUID, dep: UUID, event: str, meta: str = "") -> None:
        self._repo.add_audit(
            organization_id=org, deployment_id=dep, event_type=event,
            request_id=self._request_id, safe_metadata=meta,
        )

    def _fail(self, record, code: str, message: str) -> None:  # type: ignore[no-untyped-def]
        self._repo.transition(
            record, AiTripwireStatus.FAILED, safe_failure_code=code,
            safe_failure_message=message[:512],
        )
        self._audit(record.organization_id, record.id, "deployment_failed", code)

    def _content_hash(self, record) -> str:  # type: ignore[no-untyped-def]
        mb = self._settings.ai_tripwire_max_document_bytes
        asset: GeneratedRagDocument | GeneratedMcpResource
        if record.surface_type == SurfaceType.RAG_DOCUMENT.value:
            asset = generate_rag_document(record.decoy_kind, record.trace_id, max_bytes=mb)
        else:
            asset = generate_mcp_resource(record.decoy_kind, record.trace_id, max_bytes=mb)
        return asset.content_hash

    # -- execute: deploy + verify + activate --------------------------------------------------

    def execute(self, organization_id: UUID, deployment_id: UUID) -> None:
        record = self._repo.get_deployment(organization_id, deployment_id)
        if record.status != AiTripwireStatus.DEPLOYING.value:
            return
        preview = self._repo.load_preview(record)
        if preview is None:
            self._fail(record, "no_preview", "deployment has no preview")
            return
        max_bytes = self._settings.ai_tripwire_max_document_bytes
        try:
            if record.surface_type == SurfaceType.RAG_DOCUMENT.value:
                self._execute_rag(organization_id, record, max_bytes)
            else:
                self._execute_mcp(organization_id, record, max_bytes)
        except ConnectorError as error:
            self._fail(record, "deploy_failed", str(error))

    def _execute_rag(self, org: UUID, record, max_bytes: int) -> None:  # type: ignore[no-untyped-def]
        connector = self._repo.get_rag_connector(org, record.connector_id)
        spec = ConnSpec(
            connector.index_or_collection,
            self._repo.resolve_secret(connector.secret_ciphertext), True,
        )
        doc = generate_rag_document(record.decoy_kind, record.trace_id, max_bytes=max_bytes)
        self._audit(org, record.id, "deployment_started")
        result = self._rag.deploy_document(
            spec, collection=record.target_collection, document_id=doc.document_id,
            title=doc.title, body=doc.body, content_hash=doc.content_hash,
            metadata=doc.metadata, trace_token=record.trace_id,
        )
        verify = self._rag.verify_document(
            spec, collection=record.target_collection, external_asset_id=result.external_asset_id,
            expected_hash=doc.content_hash, trace_token=record.trace_id,
        )
        self._finish(org, record, result.external_asset_id, result.verification_hash, verify)

    def _execute_mcp(self, org: UUID, record, max_bytes: int) -> None:  # type: ignore[no-untyped-def]
        connector = self._repo.get_mcp_connector(org, record.connector_id)
        spec = ConnSpec(
            connector.server_reference,
            self._repo.resolve_secret(connector.secret_ciphertext), True,
        )
        resource = generate_mcp_resource(record.decoy_kind, record.trace_id, max_bytes=max_bytes)
        self._audit(org, record.id, "deployment_started")
        result = self._mcp.deploy_resource(
            spec, uri=resource.uri, name=resource.name, description=resource.description,
            content_hash=resource.content_hash, metadata=resource.metadata,
            trace_token=record.trace_id,
        )
        verify = self._mcp.verify_resource(
            spec, external_asset_id=result.external_asset_id,
            expected_hash=resource.content_hash, trace_token=record.trace_id,
        )
        self._finish(org, record, result.external_asset_id, result.verification_hash, verify)

    def _finish(self, org: UUID, record, asset_id: str, vhash: str, verify) -> None:  # type: ignore[no-untyped-def]
        if not (verify.exists and verify.hash_match and verify.trace_present):
            self._repo.transition(
                record, AiTripwireStatus.VERIFICATION_FAILED,
                external_asset_id=asset_id, safe_failure_code="verify_failed",
                safe_failure_message="external asset failed verification",
            )
            self._audit(org, record.id, "verification_failed")
            return
        self._audit(org, record.id, "deployment_succeeded")
        self._audit(org, record.id, "verification_passed")
        now = datetime.now(UTC)
        # Monitoring activates only after verification.
        self._repo.transition(
            record, AiTripwireStatus.DEPLOYED, external_asset_id=asset_id,
            verification_hash=vhash, deployed_at=now, monitoring_activated_at=now,
        )
        self._audit(org, record.id, "monitoring_activated", f"trace={record.trace_id}")

    # -- retire: delete only the owned asset --------------------------------------------------

    def retire(self, organization_id: UUID, deployment_id: UUID) -> None:
        record = self._repo.get_deployment(organization_id, deployment_id)
        if record.status != AiTripwireStatus.RETIRING.value:
            return
        if record.external_asset_id is None:
            self._repo.transition(record, AiTripwireStatus.RETIRED, retired_at=datetime.now(UTC))
            self._audit(organization_id, deployment_id, "retirement_completed")
            return
        self._audit(organization_id, deployment_id, "retirement_started")
        expected = self._content_hash(record)
        try:
            if record.surface_type == SurfaceType.RAG_DOCUMENT.value:
                rag = self._repo.get_rag_connector(organization_id, record.connector_id)
                spec = ConnSpec(
                    rag.index_or_collection,
                    self._repo.resolve_secret(rag.secret_ciphertext), True,
                )
                outcome = self._rag.delete_document(
                    spec, collection=record.target_collection,
                    external_asset_id=record.external_asset_id, expected_hash=expected,
                )
            else:
                mcp = self._repo.get_mcp_connector(organization_id, record.connector_id)
                spec = ConnSpec(
                    mcp.server_reference,
                    self._repo.resolve_secret(mcp.secret_ciphertext), True,
                )
                outcome = self._mcp.retire_resource(
                    spec, external_asset_id=record.external_asset_id, expected_hash=expected,
                )
        except ConnectorError as error:
            self._fail(record, "delete_failed", str(error))
            return
        if outcome.drift:
            self._repo.transition(
                record, AiTripwireStatus.DRIFT_DETECTED, safe_failure_code="asset_drift",
                safe_failure_message="external asset changed; manual review required",
            )
            self._audit(organization_id, deployment_id, "drift_detected")
            return
        self._repo.transition(record, AiTripwireStatus.RETIRED, retired_at=datetime.now(UTC))
        self._audit(organization_id, deployment_id, "retirement_completed")

    # -- monitoring: severity signal on repeated exposure -------------------------------------

    def note_activation_incomplete(self, org: UUID, deployment_id: UUID) -> None:
        emit(
            "ai_tripwire_activation_failed", severity="high",
            deployment_id=str(deployment_id),
            organization_id=str(org),
        )
