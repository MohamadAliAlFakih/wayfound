"""Pydantic schemas for the Phase 4 /trips/plan endpoint.

D-19: PlanTripRequest — validated request body
D-20: PlanTripResponse + ToolCallOut — synchronous full payload
D-21: ExtractedFields — output of extraction_node (8b structured output)
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class PlanTripRequest(BaseModel):
    """Request body for POST /trips/plan (D-19)."""

    query: str = Field(min_length=10, max_length=2000)


class ExtractedFields(BaseModel):
    """8b extraction node output (D-21).

    Every field is optional — D-22 says extraction failures don't fail the
    request. Defaults make the model behave as a partial-fields container
    that downstream nodes can read safely.
    """

    budget_per_day_usd: float | None = Field(
        default=None,
        description="Per-day USD budget. If user gave a total + duration, divide.",
    )
    duration_days: int | None = Field(default=None, ge=1, le=365)
    preferred_climate: str | None = Field(
        default=None,
        description="One of: warm, cold, temperate. Null if not stated.",
    )
    origin: str | None = Field(default=None, description="Origin city name.")
    preferences: list[str] = Field(
        default_factory=list,
        description="e.g. hiking, beach, culture, food, nightlife, history, family.",
    )
    departure_date: str | None = Field(
        default=None, description="ISO 8601 date (YYYY-MM-DD) if specific date given."
    )
    return_date: str | None = Field(
        default=None, description="ISO 8601 date (YYYY-MM-DD)."
    )


class ToolCallOut(BaseModel):
    """One ToolCall row in the response payload (D-20)."""

    tool_name: str
    input: dict
    output: dict | list | str | None = None
    latency_ms: int | None = None
    created_at: datetime


class PlanTripResponse(BaseModel):
    """Response body for POST /trips/plan (D-20). Synchronous, full payload."""

    trip_id: UUID
    status: Literal["completed", "failed"]
    answer: str
    tool_calls: list[ToolCallOut] = Field(default_factory=list)
    created_at: datetime
    completed_at: datetime
    failure_reason: str | None = None
