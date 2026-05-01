"""create pgvector extension

Revision ID: 001
Revises:
Create Date: 2026-04-29

P-02: pgvector extension MUST exist before any subsequent migration references
the Vector type. This is the first migration in the chain.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")


def downgrade() -> None:
    op.execute("DROP EXTENSION IF EXISTS vector")
