<!-- Purpose: document the AI (RAG/MCP) tripwire lifecycle: inert decoy content, trace design,
approval, deployment/verification, minimized signed event ingestion, deterministic classification,
and retirement/drift. -->

# AI tripwires (RAG / MCP)

Deploy **inert, synthetic** decoy documents into approved RAG/vector-store collections and inert
decoy resources/configs into approved MCP servers, then detect when they are retrieved, read, or
referenced by an AI system. Everything is reversible, organization-scoped, and auditable.

Disabled by default: `AI_TRIPWIRE_DEPLOYMENT_ENABLED`, `RAG_CONNECTORS_ENABLED`,
`MCP_CONNECTORS_ENABLED`. Explicit enablement is required outside development.

## Surfaces and decoy kinds

- **RAG documents** (`rag_document`): architecture note, customer escalation summary, pricing
  exception memo, support runbook, incident handoff, roadmap excerpt, billing policy note.
- **MCP resources/configs** (`mcp_resource`, `mcp_config`): synthetic knowledge resource, inert
  configuration entry, synthetic tool description, reserved endpoint reference.

Every asset is inert: no real customer data, no real credentials, no valid internal URLs, no
executable payloads, and no prompt-injection instructions. Content safety
(`app/services/ai_tripwire/safety.py`) rejects injection/executable/URL patterns and requires the
`deceptiforge://` scheme for MCP URIs before an asset can be previewed or deployed.

## Flow

```
register connector -> test -> create deployment (+ exact preview) -> submit -> approve
  -> deploy -> [worker: deploy through adapter + verify external asset + trace -> activate monitoring]
deployed -> ingest signed minimized events -> deterministic classification
deployed -> retire (delete only the owned asset) ; drift -> drift_detected (manual review)
```

The state machine (`app/models/domain/ai_tripwire.py`) rejects illegal transitions (409).
**Monitoring activates only after verification** — if the external asset id, content hash, or trace
cannot be verified, the deployment becomes `verification_failed` and no monitoring is registered.

Permissions: `ai_tripwire_connectors:{read,manage}`,
`ai_tripwires:{read,create,approve,deploy,retire,ingest}`. Separation of duties
(`REQUIRE_SEPARATE_AI_TRIPWIRE_APPROVER`) prevents the requester from approving their own
deployment. GPT never decides deployment safety and never assigns severity.

## Trace design

A trace must remain detectable after chunking, embedding, retrieval, excerpting, summarization, and
partial copying, so multiple mechanisms are combined (`app/services/ai_tripwire/trace.py`):

- an explicit synthetic reference token (`DFAI-<hex>`), re-emitted roughly every 400 characters so
  chunk boundaries still carry it;
- reserved phrases embedded in benign prose;
- a structured metadata field (`deceptiforge_trace`);
- a stable document id / reserved MCP URI.

Detection does not rely on a single exact full-string match. **False-positive tradeoff:** short or
common markers raise false positives; the reference token is deliberately distinctive, and events
are only trusted from signed monitors, so a stray textual match alone is not treated as ingestion.

## Deterministic classification

Exposure category and severity are computed deterministically
(`app/services/ai_tripwire/classification.py`) from the deployment's minimized events —
`rag_retrieval_exposure`, `rag_answer_leak`, `mcp_resource_access`, `mcp_config_exposure`,
`ai_agent_decoy_touch`, or `multi_surface_ai_exposure`. Severity starts from the category and is
bumped for repetition, multiple distinct sources, and multiple surfaces. No model is consulted.

## Retirement and drift

Retirement deletes **only the owned external asset** after regenerating the exact content hash and
confirming ownership. If the external asset changed, the deployment becomes `drift_detected` and is
**not** deleted automatically — manual review is required.

## Unsupported

No autonomous offensive agents, no prompt-injection payload generation, no model jailbreaks, no
unsafe tool execution, no arbitrary code execution, no broad browser monitoring, no direct mutation
of production systems without an explicit connector policy. First release supports one connector per
surface via deterministic in-memory fake adapters (see [RAG](integrations/RAG.md) and
[MCP](integrations/MCP.md)); production wiring binds concrete provider clients.

See also: [AI data handling](AiDataHandling.md), [Security model](SecurityModel.md).
