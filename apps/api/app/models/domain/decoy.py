# Purpose: model compositional decoy assets and their quality assessments. Responsibilities: define typed payload shapes, placement evidence, and believability scores without generation or deployment behavior. Future modules: add secure content storage and feature-specific payload metadata.
from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field

from app.models.domain.base import (
    BelievabilityId,
    DecoyId,
    DomainModel,
    OrganizationId,
    PlacementId,
    RepositoryId,
    RepositoryProfileId,
)
from app.models.domain.organization import RiskLevel


class DecoyKind(StrEnum):
    """The material form of a decoy payload."""

    SECRET = "secret"
    DATABASE_RECORD = "database_record"
    DOCUMENT = "document"
    SPREADSHEET_ROW = "spreadsheet_row"
    MCP_CONFIG = "mcp_config"
    EMBEDDING = "embedding"
    AGENT_ASSET = "agent_asset"


class DecoyState(StrEnum):
    """Lifecycle states for a decoy envelope."""

    DRAFT = "draft"
    ACTIVE = "active"
    RETIRED = "retired"


class Priority(StrEnum):
    """Placement execution order without implying operational behavior."""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


class PlacementTargetKind(StrEnum):
    """Supported target surfaces for future placement execution."""

    REPOSITORY_PATH = "repository_path"
    DATABASE_TABLE = "database_table"
    DOCUMENT_STORE = "document_store"
    SPREADSHEET = "spreadsheet"
    MCP_SERVER = "mcp_server"
    VECTOR_INDEX = "vector_index"
    AGENT_WORKSPACE = "agent_workspace"


class DocumentFormat(StrEnum):
    """Document formats recognized by document-shaped decoys."""

    TEXT = "text"
    MARKDOWN = "markdown"
    PDF = "pdf"
    DOCX = "docx"


class McpTransport(StrEnum):
    """Transport categories for an MCP configuration decoy."""

    STDIO = "stdio"
    SSE = "sse"
    STREAMABLE_HTTP = "streamable_http"


class AgentAssetKind(StrEnum):
    """Agent-facing artifact forms represented by decoys."""

    INSTRUCTION = "instruction"
    TOOL_DEFINITION = "tool_definition"
    MEMORY = "memory"
    SKILL = "skill"


class ContentReference(DomainModel):
    """Reference to protected decoy material.

    Purpose: identify encrypted material without exposing it in domain serialization.
    Fields: opaque locator, content digest, and media type.
    Relationships: embedded by payloads; the future asset store owns the referenced bytes.
    Future extensibility: add key version and retention metadata without storing raw content.
    """

    locator: str = Field(min_length=1, max_length=2048)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    media_type: str = Field(min_length=1, max_length=255)


class DecoyPayloadBase(DomainModel):
    """Base interface for all composable decoy payloads.

    Purpose: establish the minimum safe contract every decoy material form shares.
    Fields: a discriminating kind and protected content reference.
    Relationships: embedded by Decoy; concrete payloads refine the discriminator and add shape metadata.
    Future extensibility: introduce a new payload kind as a new concrete class, never as nullable fields here.
    """

    kind: DecoyKind
    content: ContentReference


class DecoyField(DomainModel):
    """A non-secret, typed structural field in a record-shaped payload.

    Purpose: express schema shape without accepting arbitrary unvalidated objects.
    Fields: field name, declared data type, and a redacted display value.
    Relationships: embedded by database and spreadsheet payloads.
    Future extensibility: add database-native type metadata as an explicit field.
    """

    name: str = Field(min_length=1, max_length=255)
    data_type: str = Field(min_length=1, max_length=128)
    display_value: str = Field(min_length=1, max_length=2048)


class SecretPayload(DecoyPayloadBase):
    """Secret-shaped decoy metadata.

    Purpose: represent a secret without serializing its material value.
    Fields: secret kind, redacted display value, fingerprint, and protected content reference.
    Relationships: composed by Decoy when kind is secret.
    Future extensibility: add provider-specific secret metadata without exposing credentials.
    """

    kind: Literal[DecoyKind.SECRET] = DecoyKind.SECRET
    secret_kind: str = Field(min_length=1, max_length=128)
    redacted_value: str = Field(min_length=1, max_length=512)
    fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    content: ContentReference


class DatabaseRecordPayload(DecoyPayloadBase):
    """Database-record-shaped decoy metadata.

    Purpose: represent a credible row shape without coupling to a database engine.
    Fields: schema, table, primary-key hint, fields, and protected serialized record reference.
    Relationships: composed by Decoy when kind is database_record.
    Future extensibility: add dialect and constraint metadata explicitly.
    """

    kind: Literal[DecoyKind.DATABASE_RECORD] = DecoyKind.DATABASE_RECORD
    schema_name: str = Field(min_length=1, max_length=255)
    table_name: str = Field(min_length=1, max_length=255)
    primary_key_hint: str = Field(min_length=1, max_length=255)
    fields: tuple[DecoyField, ...] = Field(min_length=1)
    content: ContentReference


class DocumentPayload(DecoyPayloadBase):
    """Document-shaped decoy metadata.

    Purpose: identify a believable document artifact without exposing its body.
    Fields: filename, format, title, and protected content reference.
    Relationships: composed by Decoy when kind is document.
    Future extensibility: add authoring and retention metadata when a document store is introduced.
    """

    kind: Literal[DecoyKind.DOCUMENT] = DecoyKind.DOCUMENT
    filename: str = Field(min_length=1, max_length=512)
    format: DocumentFormat
    title: str = Field(min_length=1, max_length=512)
    content: ContentReference


class SpreadsheetRowPayload(DecoyPayloadBase):
    """Spreadsheet-row-shaped decoy metadata.

    Purpose: represent a credible row while keeping workbook bytes protected.
    Fields: workbook name, sheet name, row index, fields, and content reference.
    Relationships: composed by Decoy when kind is spreadsheet_row.
    Future extensibility: add table range or formula metadata as separate optional fields.
    """

    kind: Literal[DecoyKind.SPREADSHEET_ROW] = DecoyKind.SPREADSHEET_ROW
    workbook_name: str = Field(min_length=1, max_length=512)
    sheet_name: str = Field(min_length=1, max_length=255)
    row_index: int = Field(ge=1)
    fields: tuple[DecoyField, ...] = Field(min_length=1)
    content: ContentReference


class McpConfigPayload(DecoyPayloadBase):
    """MCP-configuration-shaped decoy metadata.

    Purpose: model a realistic MCP configuration without leaking executable configuration values.
    Fields: server name, transport, redacted endpoint, and protected config reference.
    Relationships: composed by Decoy when kind is mcp_config.
    Future extensibility: add capability declarations after an MCP integration exists.
    """

    kind: Literal[DecoyKind.MCP_CONFIG] = DecoyKind.MCP_CONFIG
    server_name: str = Field(min_length=1, max_length=255)
    transport: McpTransport
    redacted_endpoint: str = Field(min_length=1, max_length=2048)
    content: ContentReference


class EmbeddingPayload(DecoyPayloadBase):
    """Embedding-shaped decoy metadata.

    Purpose: locate a protected vector artifact without serializing raw vectors.
    Fields: index name, vector dimensions, content reference, and content digest.
    Relationships: composed by Decoy when kind is embedding.
    Future extensibility: add embedding-model identity and namespace metadata.
    """

    kind: Literal[DecoyKind.EMBEDDING] = DecoyKind.EMBEDDING
    index_name: str = Field(min_length=1, max_length=255)
    dimensions: int = Field(ge=1, le=65536)
    content: ContentReference


class AgentAssetPayload(DecoyPayloadBase):
    """Agent-facing asset decoy metadata.

    Purpose: represent an instruction, tool, memory, or skill artifact safely.
    Fields: asset kind, display name, description, and protected content reference.
    Relationships: composed by Decoy when kind is agent_asset.
    Future extensibility: add agent-runtime compatibility metadata once a target runtime is approved.
    """

    kind: Literal[DecoyKind.AGENT_ASSET] = DecoyKind.AGENT_ASSET
    asset_kind: AgentAssetKind
    name: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1, max_length=2000)
    content: ContentReference


DecoyPayload = Annotated[
    SecretPayload
    | DatabaseRecordPayload
    | DocumentPayload
    | SpreadsheetRowPayload
    | McpConfigPayload
    | EmbeddingPayload
    | AgentAssetPayload,
    Field(discriminator="kind"),
]


class Decoy(DomainModel):
    """Core decoy envelope composed with a typed payload.

    Purpose: provide one durable identity and lifecycle for all decoy forms.
    Fields: ownership IDs, profile context, state, typed payload, and schema revision.
    Relationships: belongs to Organization, may reference Repository/Profile, and has Placement and Believability records.
    Future extensibility: add deployment references and retirement reasons without changing payload semantics.
    """

    id: DecoyId
    organization_id: OrganizationId
    repository_id: RepositoryId | None = None
    repository_profile_id: RepositoryProfileId | None = None
    state: DecoyState
    payload: DecoyPayload
    schema_version: int = Field(default=1, ge=1)


class PlacementTarget(DomainModel):
    """A concrete future deployment surface.

    Purpose: locate a decoy without implementing placement behavior.
    Fields: target kind, opaque locator, and optional repository relation.
    Relationships: embedded by Placement and may reference Repository.
    Future extensibility: add provider-native identity fields for target kinds that need them.
    """

    kind: PlacementTargetKind
    locator: str = Field(min_length=1, max_length=2048)
    repository_id: RepositoryId | None = None


class Placement(DomainModel):
    """Placement recommendation and expected detection value.

    Purpose: preserve where and why a decoy should be deployed.
    Fields: target, confidence, reason, priority, risk, and expected detection quality.
    Relationships: belongs to one Decoy; target may refer to a Repository.
    Future extensibility: add execution status as a separate deployment aggregate.
    """

    id: PlacementId
    decoy_id: DecoyId
    target: PlacementTarget
    confidence: float = Field(ge=0, le=1)
    reason: str = Field(min_length=1, max_length=4000)
    priority: Priority
    risk: RiskLevel
    expected_detection_quality: float = Field(ge=0, le=1)
    schema_version: int = Field(default=1, ge=1)


class Believability(DomainModel):
    """Explainable score breakdown for one decoy.

    Purpose: retain human-reviewable quality evidence without calculating scores in the model.
    Fields: naming, entropy, context, schema, placement, overall scores, and explanation.
    Relationships: belongs to one Decoy and can be evaluated against its Placement.
    Future extensibility: add evaluator version and factor-level evidence IDs.
    """

    id: BelievabilityId
    decoy_id: DecoyId
    naming_score: float = Field(ge=0, le=1)
    entropy_score: float = Field(ge=0, le=1)
    context_score: float = Field(ge=0, le=1)
    schema_score: float = Field(ge=0, le=1)
    placement_score: float = Field(ge=0, le=1)
    overall_score: float = Field(ge=0, le=1)
    explainability: str = Field(min_length=1, max_length=4000)
    schema_version: int = Field(default=1, ge=1)


class DecoyTemplateId(StrEnum):
    """Versioned, allow-listed templates used for deterministic generation."""

    SECRET_V1 = "secret_v1"
    DOCUMENT_V1 = "document_v1"
    DATABASE_RECORD_V1 = "database_record_v1"


class GeneratedSecret(DomainModel):
    provider_family: str = Field(min_length=1, max_length=128)
    key_name: str = Field(min_length=1, max_length=255)
    fake_value: str = Field(min_length=16, max_length=512)
    entropy_profile: str = Field(min_length=1, max_length=128)
    naming_rationale: str = Field(min_length=1, max_length=1000)
    target_file_style: str = Field(min_length=1, max_length=128)
    authentication_capability: Literal["none"] = "none"
    rotation_recommendation: str = Field(min_length=1, max_length=1000)


class GeneratedDocument(DomainModel):
    title: str = Field(min_length=1, max_length=512)
    body: str = Field(min_length=1, max_length=4000)
    target_document_type: str = Field(min_length=1, max_length=128)
    sensitivity_label: str = Field(min_length=1, max_length=128)
    trace_identifier: str = Field(min_length=1, max_length=128)


class GeneratedDatabaseRecord(DomainModel):
    table_name: str = Field(min_length=1, max_length=255)
    entity_type: str = Field(min_length=1, max_length=128)
    fields: tuple[DecoyField, ...] = Field(min_length=1)
    synthetic_data_provenance: Literal["deterministic_synthetic"] = "deterministic_synthetic"
    relationship_placeholders: tuple[str, ...] = ()
    trace_identifier: str = Field(min_length=1, max_length=128)
    no_real_person_safeguard: Literal["no_personal_data"] = "no_personal_data"
    export_detection_fingerprint: str = Field(min_length=1, max_length=128)


GeneratedDecoyPayload = GeneratedSecret | GeneratedDocument | GeneratedDatabaseRecord


class BelievabilityInputs(DomainModel):
    naming_match: float = Field(ge=0, le=1)
    entropy_profile: float = Field(ge=0, le=1)
    context_match: float = Field(ge=0, le=1)
    placement_match: float = Field(ge=0, le=1)
    schema_realism: float = Field(ge=0, le=1)
    business_realism: float = Field(ge=0, le=1)
    safety_risk: float = Field(ge=0, le=1)


class DecoySafetyMetadata(DomainModel):
    contains_real_credentials: Literal[False] = False
    contains_real_customer_data: Literal[False] = False
    safe_for_demo: Literal[True] = True
    authentication_capability: Literal["none"] = "none"


class CollisionCheckMetadata(DomainModel):
    checked_names: tuple[str, ...] = ()
    collision_detected: bool
    reasons: tuple[str, ...] = ()


class TriggerMetadataPlaceholder(DomainModel):
    trace_identifier: str = Field(min_length=1, max_length=128)
    monitoring_status: Literal["not_configured"] = "not_configured"


class RotationMetadata(DomainModel):
    expires_at: str | None = None
    rotation_recommendation: str = Field(min_length=1, max_length=1000)


class DecoyValidationResult(DomainModel):
    valid: bool
    checks: tuple[str, ...] = ()
    reasons: tuple[str, ...] = ()


class DecoyAsset(DomainModel):
    decoy_id: UUID
    decoy_type: DecoyKind
    target_placement_id: UUID
    target_location: str = Field(min_length=1, max_length=2048)
    payload: GeneratedDecoyPayload
    template_id: DecoyTemplateId
    believability_inputs: BelievabilityInputs
    safety_metadata: DecoySafetyMetadata
    collision_check: CollisionCheckMetadata
    trigger_metadata: TriggerMetadataPlaceholder
    rotation_metadata: RotationMetadata
    explanation: tuple[str, ...] = Field(min_length=1)
    validation: DecoyValidationResult


class RejectedGenerationCandidate(DomainModel):
    target_location: str = Field(min_length=1, max_length=2048)
    reasons: tuple[str, ...] = Field(min_length=1)


class DecoyGenerationPlan(DomainModel):
    repository_name: str = Field(min_length=1, max_length=256)
    assets: tuple[DecoyAsset, ...] = ()
    rejected_candidates: tuple[RejectedGenerationCandidate, ...] = ()


class BelievabilityDecision(StrEnum):
    ACCEPT = "accept"
    WARN = "warn"
    REJECT = "reject"


class BelievabilityScoreBreakdown(DomainModel):
    naming_realism: float = Field(ge=0, le=100)
    context_fit: float = Field(ge=0, le=100)
    placement_compatibility: float = Field(ge=0, le=100)
    schema_completeness: float = Field(ge=0, le=100)
    entropy_realism: float = Field(ge=0, le=100)
    business_realism: float = Field(ge=0, le=100)
    traceability_quality: float = Field(ge=0, le=100)
    safety_inertness: float = Field(ge=0, le=100)
    production_collision_risk: float = Field(ge=0, le=100)
    accidental_use_risk: float = Field(ge=0, le=100)
    obvious_trap_risk: float = Field(ge=0, le=100)


class BelievabilitySafetyReport(DomainModel):
    decoy_id: UUID
    overall_believability_score: float = Field(ge=0, le=100)
    overall_safety_score: float = Field(ge=0, le=100)
    decision: BelievabilityDecision
    breakdown: BelievabilityScoreBreakdown
    explainability_notes: tuple[str, ...] = ()
    failed_checks: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    recommended_fixes: tuple[str, ...] = ()
