"""Service-layer orchestrator for POST /trips/plan (D-14..D-26, AGT-05, WH-01..03).

Flow:
  1. INSERT Trip(status='running') eagerly; commit so trip_id is stable.
  2. Run app.state.graph.ainvoke with:
       - initial state (system + human messages, query, user_id, trip_id)
       - config: recursion_limit, callbacks=[TokenAccumulator],
         configurable={extraction_llm, agent_llm, tools, session_factory}
  3. Catch GraphRecursionError → status='failed', failure_reason='turn_limit'.
     Catch other Exception → status='failed', failure_reason='graph_error'.
  4. UPDATE Trip with answer + tool_names + completed_at + status.
  5. SELECT ToolCalls for response payload.
  6. Schedule fire-and-forget Discord delivery (P-02 strong-ref pattern).
  7. Return PlanTripResponse.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.errors import GraphRecursionError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.callbacks import TokenAccumulator
from app.agents.graph import RECURSION_LIMIT
from app.agents.prompts import AGENT_SYSTEM_PROMPT
from app.core.settings import settings
from app.models.tool_call import ToolCall
from app.models.trip import Trip
from app.models.user import User
from app.schemas.trips import PlanTripRequest, PlanTripResponse, ToolCallOut
from app.webhooks.discord import build_discord_embed, deliver_webhook

logger = logging.getLogger(__name__)


def _extract_summary_for_embed(messages: list[Any]) -> tuple[str | None, str | None]:
    """Best-effort scan of ToolMessages for travel_style + top_destination,
    used in the Discord embed (D-23). Returns (travel_style, top_destination)."""
    travel_style: str | None = None
    top_destination: str | None = None
    for msg in messages:
        content = getattr(msg, "content", None)
        if not isinstance(content, str):
            continue
        # classifier_tool result is JSON-serialized dict; parse opportunistically.
        if travel_style is None and '"travel_style"' in content:
            try:
                data = json.loads(content)
                if isinstance(data, dict) and "travel_style" in data:
                    travel_style = str(data["travel_style"])
            except (json.JSONDecodeError, ValueError, TypeError):
                pass
        # rag_tool result: list of dicts with 'destination' key — first one.
        if top_destination is None and '"destination"' in content:
            try:
                data = json.loads(content)
                if isinstance(data, list) and data:
                    first = data[0]
                    if isinstance(first, dict) and "destination" in first:
                        top_destination = str(first["destination"])
            except (json.JSONDecodeError, ValueError, TypeError):
                pass
    return travel_style, top_destination


async def _load_tool_calls(session: AsyncSession, trip_id: Any) -> list[ToolCallOut]:
    """SELECT all ToolCall rows for the trip, ordered by created_at, mapped to ToolCallOut."""
    stmt = (
        select(ToolCall)
        .where(ToolCall.trip_id == trip_id)
        .order_by(ToolCall.created_at)
    )
    result = await session.execute(stmt)
    rows = result.scalars().all()
    return [
        ToolCallOut(
            tool_name=r.tool_name,
            input=r.input_json or {},
            output=r.output_json,
            latency_ms=r.latency_ms,
            created_at=r.created_at,
        )
        for r in rows
    ]


def _schedule_webhook(app: FastAPI, payload: dict[str, Any]) -> None:
    """Fire-and-forget Discord delivery with strong-ref + done-callback (P-02)."""
    if settings.discord_webhook_url is None:
        logger.info("DISCORD_WEBHOOK_URL not set; skipping webhook (D-26)")
        return
    url = str(settings.discord_webhook_url)
    if getattr(app.state, "background_tasks", None) is None:
        # Defensive: lifespan should have created this set; create it lazily.
        app.state.background_tasks = set()
    task = asyncio.create_task(deliver_webhook(url, payload))
    app.state.background_tasks.add(task)              # P-02: strong-ref so task isn't GC'd
    task.add_done_callback(app.state.background_tasks.discard)  # P-02: auto-clean on completion


async def plan_trip(
    req: PlanTripRequest,
    user: User,
    app: FastAPI,
    session: AsyncSession,
) -> PlanTripResponse:
    """Orchestrate one /trips/plan call. Returns PlanTripResponse on both
    success and failure (OQ-3 — 200 with status='failed' on turn_limit)."""

    # 1. Eager Trip insert (D-14)
    trip = Trip(
        user_id=user.id,
        query=req.query,
        tool_names=[],
        # status defaults to 'running' via server_default (Plan 04-01 D-16)
    )
    session.add(trip)
    await session.commit()
    await session.refresh(trip)
    trip_id = trip.id
    logger.info("plan_trip start trip_id=%s user_id=%s", trip_id, user.id)

    # 2. Build initial state. Extraction is the FIRST graph node, so we don't
    #    pre-populate extraction-derived fields here — extraction_node merges
    #    them into state before llm_node runs.
    initial_state: dict[str, Any] = {
        "messages": [
            SystemMessage(content=AGENT_SYSTEM_PROMPT),
            HumanMessage(content=req.query),
        ],
        "query": req.query,
        "user_id": str(user.id),
        "trip_id": str(trip_id),
        "preferences": [],
    }

    # 3. Build config: callbacks + configurable injections
    accumulator = TokenAccumulator()
    # Build a name-keyed dict of bound tools — graph's tools_node reads this.
    tools_list = list(getattr(app.state, "agent_tools", []))
    tools_map = {t.name: t for t in tools_list}
    config = {
        "recursion_limit": RECURSION_LIMIT,
        "callbacks": [accumulator],
        "configurable": {
            "extraction_llm": app.state.extraction_llm,
            "agent_llm": app.state.agent_llm,
            "tools": tools_map,
            "session_factory": app.state.db_session_factory,
        },
    }

    # 4. Run graph; catch failure modes
    final_state: dict[str, Any] | None = None
    failure_reason: str | None = None
    try:
        final_state = await app.state.graph.ainvoke(initial_state, config=config)
    except GraphRecursionError:
        failure_reason = "turn_limit"
        logger.warning("plan_trip trip_id=%s recursion_limit exceeded", trip_id)
    except Exception as exc:  # noqa: BLE001 — OQ-3: convert to status='failed', return 200
        failure_reason = "graph_error"
        logger.warning("plan_trip trip_id=%s graph error: %s", trip_id, exc)

    # 5. Compose final answer + tool_names from graph state (or fallback)
    answer: str
    tool_names: list[str] = []
    if final_state is not None:
        messages = final_state.get("messages") or []
        # Final answer = last AIMessage with content (no tool_calls)
        answer = ""
        for msg in reversed(messages):
            tc = getattr(msg, "tool_calls", None)
            content = getattr(msg, "content", None)
            if isinstance(content, str) and content and not tc:
                answer = content
                break
        if not answer:
            answer = (
                "I couldn't compose a final plan within the allowed turns. "
                "Please try a more specific query."
            )
        # Ordered unique tool names from ToolMessages (preserves call order)
        seen: set[str] = set()
        for msg in messages:
            name = getattr(msg, "name", None)
            if isinstance(name, str) and name and name not in seen:
                tool_names.append(name)
                seen.add(name)
    else:
        answer = (
            "The plan could not be completed (turn limit or internal error)."
            if failure_reason
            else "Unknown failure."
        )

    # 6. UPDATE trip with final state
    completed_at = datetime.now(timezone.utc)
    trip.answer = answer
    trip.tool_names = tool_names
    trip.completed_at = completed_at
    trip.status = "failed" if failure_reason else "completed"
    trip.failure_reason = failure_reason
    await session.commit()
    await session.refresh(trip)

    # 7. Build response payload (re-read tool calls so latency/output reflect
    #    what the tracker wrote during the graph run).
    tool_call_outs = await _load_tool_calls(session, trip_id)

    # 8. Schedule Discord webhook (P-02 strong-ref pattern, D-25, D-26)
    if settings.discord_webhook_url is not None:
        travel_style, top_destination = _extract_summary_for_embed(
            final_state.get("messages") if final_state else []
        )
        embed_payload = build_discord_embed(
            trip_id=trip_id,
            status=trip.status,
            answer=answer,
            tool_names=tool_names,
            travel_style=travel_style,
            top_destination=top_destination,
            total_tokens=accumulator.total_tokens,
            cost_usd=accumulator.total_cost_usd,
            completed_at=completed_at,
        )
        _schedule_webhook(app, embed_payload)

    logger.info(
        "plan_trip done trip_id=%s status=%s tools=%s tokens=%d cost=$%.6f",
        trip_id,
        trip.status,
        tool_names,
        accumulator.total_tokens,
        accumulator.total_cost_usd,
    )

    return PlanTripResponse(
        trip_id=trip_id,
        status=trip.status,  # type: ignore[arg-type]  # runtime value is 'completed' or 'failed'
        answer=answer,
        tool_calls=tool_call_outs,
        created_at=trip.created_at,
        completed_at=completed_at,
        failure_reason=failure_reason,
    )
