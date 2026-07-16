<!-- Purpose: document stable core-domain contracts. Responsibilities: explain model intent, fields, relationships, and extension rules. Future modules: add sections as approved aggregates are introduced. -->

# Core Domain Model

## Design rules

Domain models are strict, immutable Pydantic contracts. They serialize consistently for API responses, JSON/JSONB database columns, and future event envelopes. Relationships use typed IDs, not nested aggregates, except immutable evidence records embedded in a repository profile snapshot.

The TypeScript contracts mirror the serialized shape. Python is the validation authority; TypeScript prevents consumer-side type drift but does not validate untrusted data.

## Organization

**Purpose:** the tenant and security-isolation boundary. **Fields:** ID, name, DNS-safe slug, creation timestamp, and schema version. **Relationships:** owns repositories. **Future extensibility:** add policy references or membership through separate aggregates, never directly to this model.

## Repository

**Purpose:** stable source-control identity without retaining source content. **Fields:** organization ID, provider identity, provider repository ID, canonical URL, default branch, and lifecycle timestamps. **Relationships:** belongs to one organization and has immutable profile snapshots. **Future extensibility:** add provider-installation or archival references explicitly.

## RepositoryProfile

**Purpose:** point-in-time contextual evidence for later generation, placement, and coverage work. **Fields:** repository revision; language, framework, service, infrastructure, and technology detections; cloud and environment naming conventions; statistics; risks; naming patterns. **Relationships:** belongs to one repository; nested evidence records are snapshot data, not independent entities. **Future extensibility:** add distinct evidence categories or detector metadata—never reinterpret an existing field.

## Embedded records

`TechnologyEvidence`, `RiskArea`, and `NamingPattern` provide provenance and confidence. `RepositoryStatistics` is a measurable snapshot. They are intentionally embedded, because splitting them into tables would make one profile revision mutable and break auditability.

## Decoy

**Purpose:** one durable envelope for every deployed or proposed decoy. **Fields:** ownership/context IDs, state, a discriminated payload, and schema version. **Relationships:** belongs to an organization; may reference the repository/profile that supplied its context; has placement and believability records. **Future extensibility:** deployment status belongs in a separate aggregate, preserving this model's content identity.

### Composed payloads

`SecretPayload`, `DatabaseRecordPayload`, `DocumentPayload`, `SpreadsheetRowPayload`, `McpConfigPayload`, `EmbeddingPayload`, and `AgentAssetPayload` share no base table or inherited behavior. Each is selected by the `kind` discriminator and contains only safe metadata plus a `ContentReference`. Raw decoy material is deliberately excluded from API, JSONB, and event serialization; a future encrypted asset store owns it.

## Placement

**Purpose:** preserve a recommendation for where and why a decoy belongs. **Fields:** target, confidence, reason, priority, risk, and expected detection quality. **Relationships:** belongs to a decoy; its target may reference a repository. **Future extensibility:** deployment execution and status remain separate so recommendations are immutable evidence.

## Believability

**Purpose:** retain a human-reviewable scoring breakdown. **Fields:** naming, entropy, context, schema, placement, and overall scores plus an explanation. **Relationships:** belongs to one decoy and may be evaluated against its placement. **Future extensibility:** evaluator version and individual evidence references can be added without altering score meaning.

## TimelineEvent

**Purpose:** the canonical immutable observation for read, copy, export, paste, index, embed, authentication, tool call, database query, package install, and document access. **Fields:** source, timestamp, target, optional actor/decoy references, confidence, and bounded safe attributes. **Relationships:** alerts reference an event; incidents embed a portable event snapshot. **Future extensibility:** add correlation and external event IDs without changing action meaning.

## Alert

**Purpose:** one normalized actionable detection. **Fields:** severity, source, timestamp, confidence, trigger type, detection method, and timeline-event reference. **Relationships:** belongs to an organization and may reference a decoy and incident. **Future extensibility:** acknowledgement and assignment are workflow concerns and remain separate.

## Incident

**Purpose:** portable forensic assessment. **Fields:** timeline, root cause, affected assets, risk, summary, evidence references, and recommendations. **Relationships:** belongs to an organization and preserves immutable copies of its timeline facts. **Future extensibility:** state, ownership, and remediation tasks stay in separate workflow aggregates.

## Coverage

**Purpose:** measured assessment of repository, database, document, AI, and overall protection. **Fields:** normalized coverage dimensions, scope, timestamp, and schema version. **Relationships:** belongs to an organization and may be repository-scoped. **Future extensibility:** evaluator versions and evidence references can be added without redefining score semantics.

## Interfaces

The Python `Protocol` and TypeScript interfaces declare scanner, generator, engine, prompt, browser-monitor, and database-monitor boundaries. They contain no behavior, prompts, monitoring code, or runtime implementations; future adapters must conform to these contracts.

## Repository intelligence and context

`RepositoryIntelligenceProfile` is an additive scanner-output contract: languages, frameworks, services, infrastructure, database/cloud/document/MCP evidence, naming profile, secret locations, risks, and analyzer confidence. `OrganizationContextProfile` is a derived, immutable interpretation used by later decoy-generation and placement use cases. Neither model is an ORM entity or an API route payload by itself.
