"""User ORM model — D-18 schema with Python-side UUID default (OQ-2)."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class User(Base):
    """Application user. email is stored lowercased (validated at schema layer)."""

    __tablename__ = "user"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    username: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True
    )
    email: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True
    )
    password_hash: Mapped[str] = mapped_column(
        String(72), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    # Phase 4 will read trips per user; declare the back-ref now so Alembic sees it.
    trips: Mapped[list["Trip"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
