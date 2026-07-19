"""Browser AI paste sensors: managed sensor identities, one-time enrollment tokens, organization
AI policy, minimized paste events, and audit.

Purpose: add per-installation browser sensors (encrypted signing secret, separate scoped ingest
key), short-lived one-time enrollment tokens, a versioned organization AI policy, trusted minimized
paste events, and an audit log. Events never persist pasted text or conversation content.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0015_browser_sensors"
down_revision = "0014_ai_tripwires"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "browser_sensors",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("sensor_public_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("installation_id", sa.String(length=128), nullable=False),
        sa.Column("device_label", sa.String(length=128), nullable=True),
        sa.Column("browser_family", sa.String(length=32), nullable=False),
        sa.Column("extension_version", sa.String(length=32), nullable=False),
        sa.Column("secret_ciphertext", sa.Text(), nullable=False),
        sa.Column("secret_key_version", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("api_key_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("sensor_public_id", name="uq_browser_sensor_public_id"),
    )
    op.create_index("ix_browser_sensors_public_id", "browser_sensors", ["sensor_public_id"])
    op.create_index("ix_browser_sensors_installation", "browser_sensors", ["installation_id"])
    op.create_index("ix_browser_sensors_status", "browser_sensors", ["status"])

    op.create_table(
        "browser_enrollment_tokens",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("created_by_actor_id", sa.Uuid(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consumed_by_sensor_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("token_hash", name="uq_browser_enrollment_token_hash"),
    )
    op.create_index(
        "ix_browser_enrollment_tokens_hash", "browser_enrollment_tokens", ["token_hash"]
    )

    op.create_table(
        "browser_ai_policies",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("trace_match_mode", sa.String(length=16), nullable=False, server_default="exact"),
        sa.Column("local_only_mode", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "event_reporting_enabled", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        sa.Column("show_user_notification", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("allow_pause", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "min_extension_version", sa.String(length=32), nullable=False, server_default="0.1.0"
        ),
        sa.Column("policy_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("rules_data", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("organization_id", name="uq_browser_ai_policy_org"),
    )

    op.create_table(
        "browser_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("browser_sensor_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("trace_id", sa.String(length=128), nullable=False, index=True),
        sa.Column("destination_domain", sa.String(length=253), nullable=False),
        sa.Column("destination_classification", sa.String(length=16), nullable=False),
        sa.Column("event_type", sa.String(length=48), nullable=False),
        sa.Column("match_method", sa.String(length=16), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("extension_version", sa.String(length=32), nullable=False),
        sa.Column("policy_version", sa.Integer(), nullable=False),
        sa.Column("excerpt_hash", sa.String(length=128), nullable=True),
        sa.Column("minimized_metadata", sa.String(length=1024), nullable=False, server_default=""),
        sa.Column("correlation_id", sa.String(length=64), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_browser_events_trace", "browser_events", ["trace_id"])
    op.create_index("ix_browser_events_classification", "browser_events", ["destination_classification"])
    op.create_index("ix_browser_events_event_type", "browser_events", ["event_type"])
    op.create_index("ix_browser_events_correlation", "browser_events", ["correlation_id"])

    op.create_table(
        "browser_sensor_audit",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("organization_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("browser_sensor_id", sa.Uuid(), nullable=True, index=True),
        sa.Column("actor_id", sa.Uuid(), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("request_id", sa.String(length=64), nullable=False),
        sa.Column("safe_metadata", sa.String(length=1024), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_browser_sensor_audit_event_type", "browser_sensor_audit", ["event_type"])


def downgrade() -> None:
    op.drop_table("browser_sensor_audit")
    op.drop_table("browser_events")
    op.drop_table("browser_ai_policies")
    op.drop_table("browser_enrollment_tokens")
    op.drop_table("browser_sensors")
