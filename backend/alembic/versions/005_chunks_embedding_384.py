"""resize chunks.embedding from 1536 to 384 (sentence-transformers/all-MiniLM-L6-v2)

Revision ID: 005
Revises: 004
Create Date: 2026-05-01

Switching off OpenAI text-embedding-ada-002 (1536-dim) to local
sentence-transformers/all-MiniLM-L6-v2 (384-dim). Existing rows are wiped
because the embedding model changed entirely — vectors aren't compatible
across models. Re-ingest will repopulate.
"""
from typing import Sequence, Union

from alembic import op
from pgvector.sqlalchemy import Vector


revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Wipe existing rows — vectors from a different model are useless.
    op.execute("DELETE FROM chunks")
    # Drop and recreate the HNSW index since the column type changes.
    op.drop_index("ix_chunks_embedding_hnsw", table_name="chunks")
    op.alter_column(
        "chunks",
        "embedding",
        type_=Vector(384),
        existing_nullable=False,
        postgresql_using="NULL::vector(384)",
    )
    op.create_index(
        "ix_chunks_embedding_hnsw",
        "chunks",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_with={"m": 16, "ef_construction": 64},
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )


def downgrade() -> None:
    op.execute("DELETE FROM chunks")
    op.drop_index("ix_chunks_embedding_hnsw", table_name="chunks")
    op.alter_column(
        "chunks",
        "embedding",
        type_=Vector(1536),
        existing_nullable=False,
        postgresql_using="NULL::vector(1536)",
    )
    op.create_index(
        "ix_chunks_embedding_hnsw",
        "chunks",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_with={"m": 16, "ef_construction": 64},
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )