"""Incident lifecycle columns for retention and lifecycle queries.

Purpose: promote incident status and last-activity to indexed columns so the incident-lifecycle and
retention jobs can query and archive without deserializing every incident blob.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0008_incident_lifecycle_columns"
down_revision = "0007_reconstruction_queue"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("incidents", sa.Column("status", sa.String(length=16), nullable=True))
    op.add_column("incidents", sa.Column("last_seen", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_incidents_status", "incidents", ["status"])
    op.create_index("ix_incidents_last_seen", "incidents", ["last_seen"])


def downgrade() -> None:
    op.drop_index("ix_incidents_last_seen", table_name="incidents")
    op.drop_index("ix_incidents_status", table_name="incidents")
    op.drop_column("incidents", "last_seen")
    op.drop_column("incidents", "status")
