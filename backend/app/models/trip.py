"""Trip ORM model — D-19 schema. Phase 4 inserts; Phase 3 only ships table."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ARRAY, DateTime, ForeignKey, String, Text, Uuid, func
from sqlalchemy import Enum as SAEnum  # alias to avoid clashing with stdlib enum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Trip(Base):
    """A single agent run scoped to a user. tool_names + completed_at filled by Phase 4."""

    __tablename__ = "trip"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("user.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    query: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    tool_names: Mapped[list[str]] = mapped_column(
        ARRAY(String(64)), nullable=False, server_default="{}"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[str] = mapped_column(
        SAEnum("running", "completed", "failed", name="trip_status"),
        nullable=False,
        server_default="running",
    )
    failure_reason: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )

    user: Mapped["User"] = relationship(back_populates="trips")
    tool_calls: Mapped[list["ToolCall"]] = relationship(
        back_populates="trip", cascade="all, delete-orphan"
    )
