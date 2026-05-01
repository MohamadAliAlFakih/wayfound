"""add status enum and failure_reason to trip (Phase 4, D-16)

Revision ID: 004
Revises: 003
Create Date: 2026-04-30

D-16: adds Trip.status (ENUM running|completed|failed, server_default='running')
and Trip.failure_reason (String(64), nullable). The eager-insert pattern in
Plan 04-05 (D-14) relies on the server_default so request entry only sets
user_id + query + tool_names.

P-05 / OQ-3 carry-over: when graph.ainvoke raises GraphRecursionError, the
service layer sets status='failed', failure_reason='turn_limit'.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    trip_status = sa.Enum(
        "running", "completed", "failed", name="trip_status"
    )
    trip_status.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "trip",
        sa.Column(
            "status",
            trip_status,
            nullable=False,
            server_default="running",
        ),
    )
    op.add_column(
        "trip",
        sa.Column("failure_reason", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("trip", "failure_reason")
    op.drop_column("trip", "status")
    sa.Enum(name="trip_status").drop(op.get_bind(), checkfirst=True)
