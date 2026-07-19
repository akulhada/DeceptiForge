# Purpose: domain contract for PostgreSQL database connectors and honey-record deployments.
# Responsibilities: define connector/deployment statuses, the explicit deployment state machine,
#   column-sensitivity and decoy-type enums, and immutable models for schema snapshots, table
#   suitability, generated rows, and deployment previews. No database or persistence concerns here.
# Dependencies: the DomainModel base.
from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field

from app.models.domain.base import DomainModel


class ConnectorStatus(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    FAILED = "failed"
    DISABLED = "disabled"
    REVOKED = "revoked"


class HoneyDeploymentStatus(StrEnum):
    DRAFT = "draft"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    DEPLOYING = "deploying"
    DEPLOYED = "deployed"
    DEPLOYED_UNMONITORED = "deployed_unmonitored"
    VERIFICATION_FAILED = "verification_failed"
    FAILED_ACTIVATION = "failed_activation"
    FAILED = "failed"
    CANCELLED = "cancelled"
    DRIFT_DETECTED = "drift_detected"
    RETIRING = "retiring"
    RETIRED = "retired"
    ROLLBACK_PENDING = "rollback_pending"
    ROLLED_BACK = "rolled_back"
    EXPIRED = "expired"


class HoneyDecoyType(StrEnum):
    CUSTOMER = "synthetic_customer"
    INVOICE = "synthetic_invoice"
    SUBSCRIPTION = "synthetic_subscription"
    SUPPORT_TICKET = "synthetic_support_ticket"
    ORDER = "synthetic_order"
    ACCOUNT = "synthetic_account"
    TRANSACTION = "synthetic_transaction"
    INTERNAL_REFERENCE = "synthetic_internal_reference"


class ColumnSensitivity(StrEnum):
    IDENTIFIER = "identifier"
    SYNTHETIC_NAME = "synthetic_name"
    SYNTHETIC_EMAIL = "synthetic_email"
    TIMESTAMP = "timestamp"
    STATUS = "status"
    MONETARY = "monetary"
    REFERENCE_NUMBER = "reference_number"
    FREE_TEXT = "free_text"
    FOREIGN_KEY = "foreign_key"
    SECRET = "secret"
    CREDENTIAL = "credential"
    REGULATED_IDENTIFIER = "regulated_identifier"
    PAYMENT = "payment"
    HEALTH = "health"
    AUTHENTICATION = "authentication"
    UNKNOWN = "unknown"


# Column categories that make an entire table ineligible for honey records.
BLOCKING_SENSITIVITIES: frozenset[ColumnSensitivity] = frozenset(
    {
        ColumnSensitivity.SECRET,
        ColumnSensitivity.CREDENTIAL,
        ColumnSensitivity.REGULATED_IDENTIFIER,
        ColumnSensitivity.PAYMENT,
        ColumnSensitivity.HEALTH,
        ColumnSensitivity.AUTHENTICATION,
    }
)


# Explicit closed state machine. Deployment before validation/approval is blocked in the service
# layer, not encoded here. Illegal transitions are rejected.
_TRANSITIONS: dict[HoneyDeploymentStatus, frozenset[HoneyDeploymentStatus]] = {
    HoneyDeploymentStatus.DRAFT: frozenset(
        {HoneyDeploymentStatus.AWAITING_APPROVAL, HoneyDeploymentStatus.CANCELLED}
    ),
    HoneyDeploymentStatus.AWAITING_APPROVAL: frozenset(
        {
            HoneyDeploymentStatus.APPROVED,
            HoneyDeploymentStatus.REJECTED,
            HoneyDeploymentStatus.CANCELLED,
        }
    ),
    HoneyDeploymentStatus.APPROVED: frozenset(
        {HoneyDeploymentStatus.DEPLOYING, HoneyDeploymentStatus.CANCELLED}
    ),
    HoneyDeploymentStatus.DEPLOYING: frozenset(
        {
            HoneyDeploymentStatus.DEPLOYED,
            HoneyDeploymentStatus.DEPLOYED_UNMONITORED,
            HoneyDeploymentStatus.VERIFICATION_FAILED,
            HoneyDeploymentStatus.FAILED_ACTIVATION,
            HoneyDeploymentStatus.FAILED,
        }
    ),
    HoneyDeploymentStatus.DEPLOYED: frozenset(
        {
            HoneyDeploymentStatus.RETIRING,
            HoneyDeploymentStatus.ROLLBACK_PENDING,
            HoneyDeploymentStatus.DRIFT_DETECTED,
            HoneyDeploymentStatus.EXPIRED,
        }
    ),
    HoneyDeploymentStatus.DEPLOYED_UNMONITORED: frozenset(
        {
            HoneyDeploymentStatus.RETIRING,
            HoneyDeploymentStatus.ROLLBACK_PENDING,
            HoneyDeploymentStatus.EXPIRED,
        }
    ),
    HoneyDeploymentStatus.VERIFICATION_FAILED: frozenset({HoneyDeploymentStatus.ROLLBACK_PENDING}),
    HoneyDeploymentStatus.FAILED_ACTIVATION: frozenset(
        {HoneyDeploymentStatus.ROLLBACK_PENDING, HoneyDeploymentStatus.RETIRING}
    ),
    HoneyDeploymentStatus.FAILED: frozenset(
        {HoneyDeploymentStatus.AWAITING_APPROVAL, HoneyDeploymentStatus.CANCELLED}
    ),
    # Drift on a deployed row: no automatic deletion — require manual review, then retire/rollback.
    HoneyDeploymentStatus.DRIFT_DETECTED: frozenset(
        {HoneyDeploymentStatus.RETIRING, HoneyDeploymentStatus.ROLLBACK_PENDING}
    ),
    HoneyDeploymentStatus.RETIRING: frozenset(
        {
            HoneyDeploymentStatus.RETIRED,
            HoneyDeploymentStatus.DRIFT_DETECTED,
            HoneyDeploymentStatus.FAILED,
        }
    ),
    HoneyDeploymentStatus.ROLLBACK_PENDING: frozenset(
        {
            HoneyDeploymentStatus.ROLLED_BACK,
            HoneyDeploymentStatus.DRIFT_DETECTED,
            HoneyDeploymentStatus.FAILED,
        }
    ),
    HoneyDeploymentStatus.EXPIRED: frozenset({HoneyDeploymentStatus.RETIRING}),
    # Terminal states.
    HoneyDeploymentStatus.REJECTED: frozenset(),
    HoneyDeploymentStatus.CANCELLED: frozenset(),
    HoneyDeploymentStatus.RETIRED: frozenset(),
    HoneyDeploymentStatus.ROLLED_BACK: frozenset(),
}


class InvalidHoneyTransitionError(Exception):
    def __init__(self, current: HoneyDeploymentStatus, target: HoneyDeploymentStatus) -> None:
        super().__init__(f"invalid honey deployment transition: {current.value} -> {target.value}")
        self.current = current
        self.target = target


def can_transition(current: HoneyDeploymentStatus, target: HoneyDeploymentStatus) -> bool:
    return target in _TRANSITIONS.get(current, frozenset())


def assert_transition(current: HoneyDeploymentStatus, target: HoneyDeploymentStatus) -> None:
    if not can_transition(current, target):
        raise InvalidHoneyTransitionError(current, target)


# ---- schema + suitability + generation models ----------------------------------------------------


class ColumnInfo(DomainModel):
    name: str
    data_type: str
    is_nullable: bool
    is_primary_key: bool = False
    is_unique: bool = False
    is_foreign_key: bool = False
    has_default: bool = False
    is_generated: bool = False
    max_length: int | None = None
    enum_values: tuple[str, ...] = ()
    sensitivity: ColumnSensitivity = ColumnSensitivity.UNKNOWN
    comment: str | None = None


class TableInfo(DomainModel):
    schema_name: str
    table_name: str
    columns: tuple[ColumnInfo, ...]
    primary_key: tuple[str, ...] = ()
    unique_constraints: tuple[tuple[str, ...], ...] = ()
    foreign_keys: tuple[str, ...] = ()
    has_triggers: bool = False
    estimated_row_count: int = 0
    comment: str | None = None


class SchemaSnapshot(DomainModel):
    connector_id: str
    database_version: str
    tables: tuple[TableInfo, ...]
    snapshot_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class RiskFlag(DomainModel):
    code: str
    detail: str


class DatabasePlacementRecommendation(DomainModel):
    connector_id: str
    schema_name: str
    table_name: str
    score: float = Field(ge=0, le=100)
    confidence: float = Field(ge=0, le=1)
    recommended_decoy_type: HoneyDecoyType
    required_fields: tuple[str, ...]
    blocked_fields: tuple[str, ...] = ()
    risk_flags: tuple[RiskFlag, ...] = ()
    reasoning: tuple[str, ...]
    deployable: bool


class GeneratedRow(DomainModel):
    """One synthetic row. Values are inert; sensitive-looking fields carry only synthetic data."""

    trace_id: str = Field(min_length=1, max_length=128)
    columns: tuple[str, ...]
    # column -> value, JSON-serializable primitives only (str/int/float/bool/None).
    values: dict[str, str | int | float | bool | None]
    row_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")


class HoneyDeploymentPreview(DomainModel):
    deployment_id: str
    connector_id: str
    schema_name: str
    table_name: str
    snapshot_hash: str
    decoy_type: HoneyDecoyType
    columns: tuple[str, ...]
    masked_values: dict[str, str]
    trace_id: str
    row_fingerprint: str
    foreign_key_plan: tuple[str, ...] = ()
    constraint_analysis: tuple[str, ...] = ()
    workflow_trigger_risk: tuple[RiskFlag, ...] = ()
    safety_ok: bool
    warnings: tuple[str, ...] = ()
    verification_plan: str
    delete_predicate: str
    expires_at: datetime | None
    expected_monitoring_registration: tuple[str, ...]
    preview_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
