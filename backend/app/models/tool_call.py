"""ToolCall ORM model — D-20 schema. Phase 4 inserts."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, String, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ToolCall(Base):
    """Per-tool log. output_json + latency_ms nullable until tool completes."""

    __tablename__ = "tool_call"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    trip_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("trip.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tool_name: Mapped[str] = mapped_column(String(64), nullable=False)
    input_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    output_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    trip: Mapped["Trip"] = relationship(back_populates="tool_calls")
