"""Retention indexes.

Purpose: index created_at on high-volume evidence tables so age-based retention scans stay bounded.
"""

from __future__ import annotations

from alembic import op

revision = "0009_retention_indexes"
down_revision = "0008_incident_lifecycle_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_detection_events_created_at", "detection_events", ["created_at"])
    op.create_index("ix_alerts_created_at", "alerts", ["created_at"])
    op.create_index("ix_incidents_created_at", "incidents", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_incidents_created_at", table_name="incidents")
    op.drop_index("ix_alerts_created_at", table_name="alerts")
    op.drop_index("ix_detection_events_created_at", table_name="detection_events")
