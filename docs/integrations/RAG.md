<!-- Purpose: document the RAG/vector-store connector — adapter interface, credentials, idempotent
deployment, verification, collection allowlist, and the staging fake adapter. -->

# RAG / vector-store connector

DeceptiForge deploys inert synthetic decoy documents into an organization's approved vector-store
collection and detects retrieval via signed events. Disabled by default (`RAG_CONNECTORS_ENABLED`,
`AI_TRIPWIRE_DEPLOYMENT_ENABLED`).

## Adapter interface

`RagConnectorAdapter` (`app/services/ai_tripwire/connectors.py`):

- `test_connection`, `list_collections`, `health_check`
- `deploy_document` — idempotent by deterministic asset id (`rag:{collection}:{document_id}`)
- `verify_document` — reads back existence, content-hash match, and trace presence
- `delete_document` — deletes only when the content hash still matches (else reports drift)

Requirements enforced by the flow: connector credentials encrypted at rest
(`secret_cipher`), TLS outside development, organization scoping, idempotent deployment, bounded
document size (`AI_TRIPWIRE_MAX_DOCUMENT_BYTES`) and metadata, and an explicit collection allowlist
(`AI_TRIPWIRE_ALLOWED_COLLECTIONS`). A deployment targeting a collection outside the allowlist is
rejected at preview time (400). Credentials are never returned by the API or written to logs.

## First implementation

The shipped adapter is `FakeRagAdapter`, a deterministic in-memory vector store used for local
development and CI — **no paid vector store is contacted in tests**. It exercises the full contract
(deploy → verify → delete, idempotency, drift on mutation). A concrete provider client
(e.g. pgvector or a hosted store) binds the same interface in `app/api/ai_tripwire.py`
(`build_rag_adapter`) and the worker; that wiring is environment-specific.

## Recommended credentials

Use a dedicated, least-privilege API key or DB role scoped to the single decoy collection with
insert/read/delete on decoy documents only — no access to production collections, no index
administration. Rotate independently of application credentials.

## Detection events

Trusted, signed retrieval events are posted to `POST /ai-tripwire-events` (see
[AI data handling](../AiDataHandling.md)). Only minimized metadata is stored — never prompts,
retrieved chunks, model output, or raw embeddings.
