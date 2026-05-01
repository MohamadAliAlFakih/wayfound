"""Single SQLAlchemy DeclarativeBase shared by every ORM model.

P-01: Multiple Base classes silently break Alembic autogenerate. Every
model module (User, Trip, ToolCall, Chunk) MUST `from app.db.base import Base`.
"""
from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Project-wide declarative base. Do not subclass this anywhere else."""

    pass
