"""POST /trips/plan — authenticated agent endpoint (D-18, D-20).

Depends on:
  - get_current_user (Phase 3 dep) — 401 if no/bad token
  - get_db_session — async session for the eager Trip insert + ToolCall reads
  - Request.app — to access lifespan singletons (extraction_llm, agent_llm,
    agent_tools, graph, background_tasks)

Returns PlanTripResponse on both success and failure (OQ-3 — 200 with
status='failed' on turn_limit; service layer handles all internal errors
so the route never raises 5xx for graph problems).
"""
from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import get_current_user
from app.db.engine import get_db_session
from app.models.user import User
from app.schemas.trips import PlanTripRequest, PlanTripResponse
from app.services.agent import plan_trip

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/trips", tags=["trips"])


@router.post(
    "/plan",
    response_model=PlanTripResponse,
    status_code=status.HTTP_200_OK,
    summary="Plan a trip with the LangGraph agent",
    description=(
        "Submit a natural-language trip query. The agent extracts structured "
        "fields, calls tools (RAG, classifier, weather, flights, FX) up to "
        "10 LLM iterations, and returns a synthesized travel plan with the "
        "tool trace. Discord webhook fires asynchronously after the response."
    ),
    responses={
        401: {"description": "Missing or invalid Bearer token"},
        422: {"description": "Query failed Pydantic validation (length 10-2000)"},
    },
)
async def plan_endpoint(
    req: PlanTripRequest,
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> PlanTripResponse:
    """POST /trips/plan: orchestrates one agent run for the authenticated user."""
    logger.info("POST /trips/plan user_id=%s query_len=%d", user.id, len(req.query))
    return await plan_trip(req=req, user=user, app=request.app, session=session)
