# Purpose: build the exact, deterministic AI tripwire preview before any deployment.
# Responsibilities: generate the inert asset, describe trace mechanisms, verification, and
#   retirement, and compute a stable preview hash. No connector or model access.
# Dependencies: domain models, content, trace, safety, settings.
from __future__ import annotations

import hashlib
from datetime import datetime

from app.config.settings import Settings
from app.models.domain.ai_tripwire import (
    AiTripwirePreview,
    GeneratedMcpResource,
    GeneratedRagDocument,
    SurfaceType,
)
from app.services.ai_tripwire import trace as trace_mod
from app.services.ai_tripwire.content import generate_mcp_resource, generate_rag_document


class AiPreviewError(Exception):
    """Raised when a safe preview cannot be produced."""


def build_rag_preview(
    *,
    deployment_id: str,
    connector_id: str,
    target_collection: str,
    decoy_kind: str,
    trace_token: str,
    expires_at: datetime | None,
    settings: Settings,
) -> tuple[AiTripwirePreview, GeneratedRagDocument]:
    if target_collection not in settings.ai_tripwire_allowed_collections:
        raise AiPreviewError("target collection is not in the allowlist")
    doc = generate_rag_document(
        decoy_kind, trace_token, max_bytes=settings.ai_tripwire_max_document_bytes
    )
    preview = _preview(
        deployment_id=deployment_id,
        surface=SurfaceType.RAG_DOCUMENT,
        connector_id=connector_id,
        target_collection=target_collection,
        decoy_kind=decoy_kind,
        trace_token=trace_token,
        exact_content=doc.body,
        metadata=doc.metadata,
        mechanisms=trace_mod.trace_mechanisms(trace_token, doc.document_id),
        content_hash=doc.content_hash,
        expires_at=expires_at,
    )
    return preview, doc


def build_mcp_preview(
    *,
    deployment_id: str,
    connector_id: str,
    target_collection: str,
    decoy_kind: str,
    trace_token: str,
    surface: SurfaceType,
    expires_at: datetime | None,
    settings: Settings,
) -> tuple[AiTripwirePreview, GeneratedMcpResource]:
    resource = generate_mcp_resource(
        decoy_kind, trace_token, max_bytes=settings.ai_tripwire_max_document_bytes
    )
    preview = _preview(
        deployment_id=deployment_id,
        surface=surface,
        connector_id=connector_id,
        target_collection=target_collection,
        decoy_kind=decoy_kind,
        trace_token=trace_token,
        exact_content=f"{resource.uri}\n{resource.description}",
        metadata=resource.metadata,
        mechanisms=(f"reserved URI '{resource.uri}'", "structured metadata trace"),
        content_hash=resource.content_hash,
        expires_at=expires_at,
    )
    return preview, resource


def _preview(
    *,
    deployment_id: str,
    surface: SurfaceType,
    connector_id: str,
    target_collection: str,
    decoy_kind: str,
    trace_token: str,
    exact_content: str,
    metadata: dict[str, str],
    mechanisms: tuple[str, ...],
    content_hash: str,
    expires_at: datetime | None,
) -> AiTripwirePreview:
    preview_hash = hashlib.sha256(
        f"{surface.value}:{target_collection}:{content_hash}".encode()
    ).hexdigest()
    return AiTripwirePreview(
        deployment_id=deployment_id,
        surface_type=surface,
        connector_id=connector_id,
        target_collection=target_collection,
        decoy_kind=decoy_kind,
        trace_token=trace_token,
        trace_mechanisms=mechanisms,
        exact_content=exact_content,
        metadata=metadata,
        safety_ok=True,
        verification_plan="Deploy through the connector, read back the external asset id + meta "
        "+ content hash, verify the trace, then activate monitoring only after verification.",
        retirement_plan="Delete only the owned external asset id; verify deletion; disable the "
        "tripwire. A modified asset yields drift_detected and is not deleted automatically.",
        expires_at=expires_at,
        expected_monitoring_registration=(trace_token,),
        preview_hash=preview_hash,
    )
