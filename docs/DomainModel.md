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
