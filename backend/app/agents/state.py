"""AgentState TypedDict for the LangGraph agent loop (D-08)."""
from __future__ import annotations

from operator import add
from typing import Annotated, TypedDict

from langchain_core.messages import BaseMessage


class AgentState(TypedDict, total=False):
    """LangGraph state. `messages` uses operator.add reducer (AGT-01).

    `total=False` so extraction-derived fields are optional in initial
    state — extraction_node merges them in. The reducer-bearing key
    (messages) is required and must be initialised by the service layer.
    """

    messages: Annotated[list[BaseMessage], add]
    # Required at request entry
    query: str
    user_id: str
    trip_id: str
    # Extraction-derived (filled by extraction_node — D-08)
    budget_per_day_usd: float | None
    duration_days: int | None
    preferred_climate: str | None
    origin: str | None
    preferences: list[str]
    departure_date: str | None
    return_date: str | None
