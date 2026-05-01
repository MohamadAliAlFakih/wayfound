"""create user table

Revision ID: 002
Revises: 001
Create Date: 2026-04-29

D-18 schema with OQ-2 deviation: UUID PK uses Python-side default=uuid.uuid4,
NOT a SQL-level UUID-generating function default — avoids requiring the
uuid-ossp Postgres extension. The DDL therefore creates the column without
a server-side default; the application-layer default in app/models/user.py
supplies the UUID at insert time.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("username", sa.String(length=64), nullable=False, unique=True),
        sa.Column("email", sa.String(length=255), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(length=72), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_table("user")
