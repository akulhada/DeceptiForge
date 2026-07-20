"""SIEM/SOAR security integrations: integrations, transactional-outbox deliveries, dead letters,
and audit.

Purpose: add organization-scoped outbound integrations (encrypted credentials, SSRF-validated
endpoints), a transactional-outbox delivery table (idempotent, leasable, retryable), a dead-letter
table (hash + metadata retained), and an audit log. Delivery never runs in the ingestion path.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0018_security_integrations"
down_revision = "0017_coverage_engine"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "security_integrations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("integration_type", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("endpoint_reference", sa.String(length=1024), nullable=False),
        sa.Column("secret_ciphertext", sa.Text(), nullable=True),
        sa.Column("secret_key_version", sa.String(length=32), nullable=True),
        sa.Column("config_data", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("routing_data", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("payload_profile", sa.String(length=24), nullable=False, server_default="minimal"),
        sa.Column("include_narrative", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "include_coverage_events", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        sa.Column(
            "include_operational_events", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        sa.Column("minimum_severity", sa.String(length=16), nullable=False, server_default="info"),
        sa.Column("created_by_actor_id", sa.Uuid(), nullable=True),
        sa.Column("last_tested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_failure_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("safe_failure_code", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_security_integrations_type", "security_integrations", ["integration_type"])
    op.create_index("ix_security_integrations_status", "security_integrations", ["status"])

    op.create_table(
        "integration_deliveries",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("integration_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("source_type", sa.String(length=24), nullable=False),
        sa.Column("source_id", sa.String(length=128), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("event_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("idempotency_key", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="queued"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("response_status", sa.Integer(), nullable=True),
        sa.Column("safe_error_code", sa.String(length=64), nullable=True),
        sa.Column("envelope_data", sa.Text(), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("idempotency_key", name="uq_integration_delivery_idempotency"),
    )
    op.create_index("ix_integration_deliveries_status", "integration_deliveries", ["status"])
    op.create_index(
        "ix_integration_deliveries_next", "integration_deliveries", ["next_attempt_at"]
    )
    op.create_index(
        "ix_integration_deliveries_integration", "integration_deliveries", ["integration_id"]
    )
    op.create_index("ix_integration_deliveries_created", "integration_deliveries", ["created_at"])

    op.create_table(
        "integration_dead_letters",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("integration_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("delivery_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("reason_code", sa.String(length=64), nullable=False),
        sa.Column("first_failed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("final_failed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "integration_audit",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("integration_id", sa.Uuid(), nullable=True, index=True),
        sa.Column("delivery_id", sa.Uuid(), nullable=True),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("request_id", sa.String(length=64), nullable=False),
        sa.Column("safe_metadata", sa.String(length=1024), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_integration_audit_event_type", "integration_audit", ["event_type"])


def downgrade() -> None:
    op.drop_table("integration_audit")
    op.drop_table("integration_dead_letters")
    op.drop_table("integration_deliveries")
    op.drop_table("security_integrations")
