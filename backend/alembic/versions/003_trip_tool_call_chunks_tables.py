"""create trip, tool_call, and chunks tables

Revision ID: 003
Revises: 002
Create Date: 2026-04-29

D-19 (trip), D-20 (tool_call), and the Phase 2 Chunk schema (chunks) all
land in this migration so a fresh Postgres reaches the full schema via
`alembic upgrade head` alone (OQ-1 resolution).

P-02: chunks references Vector(1536); the pgvector extension was installed
in migration 001, so the type is available here.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import ARRAY, JSONB


revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- trip ---
    op.create_table(
        "trip",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=True),
        sa.Column(
            "tool_names",
            ARRAY(sa.String(length=64)),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_trip_user_id", "trip", ["user_id"])
    op.create_index(
        "ix_trip_created_at",
        "trip",
        [sa.text("created_at DESC")],
    )

    # --- tool_call ---
    op.create_table(
        "tool_call",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column(
            "trip_id",
            sa.Uuid(),
            sa.ForeignKey("trip.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("tool_name", sa.String(length=64), nullable=False),
        sa.Column("input_json", JSONB(), nullable=False),
        sa.Column("output_json", JSONB(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_tool_call_trip_id", "tool_call", ["trip_id"])

    # --- chunks (Phase 2 schema, brought into Alembic per OQ-1) ---
    op.create_table(
        "chunks",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("destination", sa.Text(), nullable=False),
        sa.Column("section", sa.Text(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("parent_id", sa.Uuid(), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(1536), nullable=False),
    )
    op.create_index("ix_chunks_destination", "chunks", ["destination"])
    op.create_index(
        "ix_chunks_embedding_hnsw",
        "chunks",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_with={"m": 16, "ef_construction": 64},
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )


def downgrade() -> None:
    op.drop_index("ix_chunks_embedding_hnsw", table_name="chunks")
    op.drop_index("ix_chunks_destination", table_name="chunks")
    op.drop_table("chunks")
    op.drop_index("ix_tool_call_trip_id", table_name="tool_call")
    op.drop_table("tool_call")
    op.drop_index("ix_trip_created_at", table_name="trip")
    op.drop_index("ix_trip_user_id", table_name="trip")
    op.drop_table("trip")
