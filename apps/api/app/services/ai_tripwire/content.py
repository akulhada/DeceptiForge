# Purpose: generate inert synthetic RAG documents and MCP resources for AI tripwires.
# Responsibilities: produce believable-but-clearly-synthetic content with an embedded, chunk-durable
#   trace and structured metadata; never include real data, credentials, or endpoints; compute a
#   content hash. Deterministic given a token + kind. Dependencies: trace, safety, domain models.
from __future__ import annotations

import hashlib

from app.models.domain.ai_tripwire import GeneratedMcpResource, GeneratedRagDocument
from app.services.ai_tripwire import trace as trace_mod
from app.services.ai_tripwire.safety import assert_safe_content, assert_safe_mcp_uri

# Inert, synthetic prose per RAG decoy kind. No real data, credentials, or endpoints.
_RAG_BODIES: dict[str, tuple[str, str]] = {
    "architecture_note": (
        "Internal architecture note (synthetic)",
        "This note summarizes a synthetic internal service topology used only for detection. "
        "Components are placeholders and reference no real hosts. Data flows are illustrative.",
    ),
    "escalation_summary": (
        "Customer escalation summary (synthetic)",
        "A synthetic escalation summary describing a fictional account issue and steps. "
        "No real customer, contact, or account is referenced. All identifiers are placeholders.",
    ),
    "pricing_exception": (
        "Pricing exception memo (synthetic)",
        "A synthetic memo describing a fictional pricing exception approval. Figures are "
        "illustrative and non-actionable. No real customer or payment detail appears here.",
    ),
    "support_runbook": (
        "Support runbook (synthetic)",
        "A synthetic support runbook with illustrative, non-executable steps for a "
        "fictional internal tool. It references no real systems and performs no actions.",
    ),
    "incident_handoff": (
        "Incident handoff (synthetic)",
        "A synthetic incident handoff describing a fictional issue and owners. Names/systems are "
        "placeholders; there is nothing to act on.",
    ),
    "roadmap_excerpt": (
        "Roadmap excerpt (synthetic)",
        "A synthetic roadmap excerpt listing fictional initiatives and quarters. Illustrative "
        "only; it reflects no real plans.",
    ),
    "billing_policy": (
        "Billing policy note (synthetic)",
        "A synthetic billing policy note with illustrative, non-actionable guidance. No real "
        "customer, invoice, or payment information appears.",
    ),
}

_MCP_KINDS: dict[str, str] = {
    "mcp_resource": "Synthetic internal knowledge resource (decoy). Inert; no real system.",
    "mcp_config": "Inert synthetic configuration entry (decoy). No executable behavior.",
    "tool_description": "Synthetic tool description (decoy). Declarative only; performs no action.",
    "endpoint_reference": "Reserved synthetic endpoint reference (decoy). Not a real endpoint.",
}


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def generate_rag_document(kind: str, trace_token: str, *, max_bytes: int) -> GeneratedRagDocument:
    if kind not in _RAG_BODIES:
        raise ValueError(f"unknown RAG decoy kind: {kind}")
    title, base = _RAG_BODIES[kind]
    document_id = f"dfai-{trace_token.split('-')[-1]}"
    body = trace_mod.embed_trace(base, trace_token)
    assert_safe_content(body, max_bytes=max_bytes)  # inert by construction; validate defensively
    metadata = {
        trace_mod.metadata_key(): trace_token,
        "synthetic": "true",
        "df_decoy_kind": kind,
        "df_document_id": document_id,
    }
    return GeneratedRagDocument(
        document_id=document_id,
        title=title,
        body=body,
        trace_token=trace_token,
        reserved_phrase=trace_mod.reserved_phrase(trace_token),
        metadata=metadata,
        content_hash=_hash(body),
    )


def generate_mcp_resource(kind: str, trace_token: str, *, max_bytes: int) -> GeneratedMcpResource:
    if kind not in _MCP_KINDS:
        raise ValueError(f"unknown MCP decoy kind: {kind}")
    uri = f"deceptiforge://decoy/{kind}/{trace_token}"
    assert_safe_mcp_uri(uri)
    description = f"{_MCP_KINDS[kind]} {trace_mod.reserved_phrase(trace_token)}"
    assert_safe_content(description, max_bytes=max_bytes)
    metadata = {
        trace_mod.metadata_key(): trace_token,
        "synthetic": "true",
        "df_decoy_kind": kind,
    }
    return GeneratedMcpResource(
        uri=uri,
        name=f"decoy-{kind}-{trace_token.split('-')[-1]}",
        description=description,
        trace_token=trace_token,
        metadata=metadata,
        content_hash=_hash(uri + description),
    )
