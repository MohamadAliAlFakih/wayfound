"""Three node functions for the LangGraph agent loop (D-02, D-03, D-22, OQ-2/P-10).

- extraction_node: 8b structured output → merge into state. D-22: failure
  logged at WARNING; returns empty dict so the graph proceeds.
- llm_node: invoke 70b agent_llm with state.messages. Returns the new
  AIMessage in a {"messages": [msg]} delta (operator.add reducer appends).
- tools_node: CUSTOM — iterates last AIMessage.tool_calls, wraps each in
  ToolCallTracker, catches per-call exceptions, returns one ToolMessage per
  tool call. P-01 mitigation: exceptions are caught here, NEVER propagate.

All three nodes accept (state, config). Required injections via
config["configurable"]:
  - extraction_llm: ChatGroq(...) bound to llama-3.1-8b-instant
  - agent_llm:      ChatGroq(...).bind_tools(...) for llama-3.3-70b-versatile
  - tools:          dict[str, StructuredTool] of allow-listed tools
  - session_factory: async_sessionmaker for ToolCallTracker
"""
from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.runnables import RunnableConfig

from app.agents.prompts import EXTRACTION_PROMPT_TEMPLATE
from app.agents.state import AgentState
from app.schemas.trips import ExtractedFields
from app.tools.tracker import ToolCallTracker

logger = logging.getLogger(__name__)


def _cfg(config: RunnableConfig | None, key: str) -> Any:
    """Read `config['configurable'][key]` with a clear error on miss."""
    cfg = (config or {}).get("configurable") or {}
    if key not in cfg:
        raise KeyError(
            f"Required runtime config '{key}' not in config['configurable']. "
            f"Service layer must pass it via graph.ainvoke(state, config={{'configurable': {{...}}}})"
        )
    return cfg[key]


async def extraction_node(
    state: AgentState, config: RunnableConfig
) -> dict[str, Any]:
    """Pre-agent extraction (D-02). Merges ExtractedFields into state on success;
    returns {} (graph proceeds) on any failure (D-22)."""
    extraction_llm = _cfg(config, "extraction_llm")
    query = state["query"]
    prompt = EXTRACTION_PROMPT_TEMPLATE.format(query=query)
    try:
        structured = extraction_llm.with_structured_output(ExtractedFields)
        fields: ExtractedFields = await structured.ainvoke(prompt)
        logger.info(
            "extraction OK: budget=%s duration=%s climate=%s prefs=%d",
            fields.budget_per_day_usd,
            fields.duration_days,
            fields.preferred_climate,
            len(fields.preferences),
        )
        return fields.model_dump()
    except Exception as exc:  # noqa: BLE001 — D-22: extraction failure does NOT fail request
        logger.warning(
            "extraction failed (proceeding with raw query only): %s", exc
        )
        return {}


async def llm_node(
    state: AgentState, config: RunnableConfig
) -> dict[str, Any]:
    """Invoke agent_llm on state.messages. Returns delta {messages: [AIMessage]}."""
    agent_llm = _cfg(config, "agent_llm")
    messages = state["messages"]
    response: AIMessage = await agent_llm.ainvoke(messages)
    return {"messages": [response]}


def _serialize_tool_output(output: Any) -> str:
    """Best-effort JSON-serialise tool output for ToolMessage.content (must be str)."""
    try:
        return json.dumps(output, default=str)
    except (TypeError, ValueError):
        return str(output)


async def tools_node(
    state: AgentState, config: RunnableConfig
) -> dict[str, Any]:
    """Custom tool runner (P-10 + D-15 + P-01 mitigation, OQ-2 deviation).

    For each tool_call in the last AIMessage:
      1. Look up the tool by name in the allowlist (D-03).
      2. Open a fresh AsyncSession, enter ToolCallTracker (INSERTs placeholder).
      3. Invoke the tool. On success → tracker.complete(result), append ToolMessage(result).
      4. On exception → tracker.fail(str(exc)), append ToolMessage with descriptive error.

    Exceptions NEVER propagate — they are converted to ToolMessages so the LLM
    sees structured error feedback and can adapt next turn (D-07, P-01).
    """
    tools_map: dict[str, Any] = _cfg(config, "tools")
    session_factory = _cfg(config, "session_factory")
    trip_id = state.get("trip_id")
    last = state["messages"][-1]
    tool_calls = getattr(last, "tool_calls", None) or []

    out_messages: list[ToolMessage] = []
    for call in tool_calls:
        name = call.get("name") or ""
        args = call.get("args") or {}
        call_id = call.get("id") or "unknown"

        tool = tools_map.get(name)
        if tool is None:
            # AGT-03: explicit allowlist refusal.
            logger.warning(
                "tools_node: refused unknown tool %r (not in allowlist)", name
            )
            out_messages.append(
                ToolMessage(
                    content=(
                        f"Error: tool {name!r} is not in the allowlist. "
                        f"Available: rag_tool, classifier_tool, weather_tool, fx_tool."
                    ),
                    tool_call_id=call_id,
                    name=name or "unknown",
                )
            )
            continue

        async with session_factory() as session:
            async with ToolCallTracker(session, trip_id, name, args) as tracker:
                try:
                    result = await tool.ainvoke(args)
                    await tracker.complete(result)
                    out_messages.append(
                        ToolMessage(
                            content=_serialize_tool_output(result),
                            tool_call_id=call_id,
                            name=name,
                        )
                    )
                except Exception as exc:  # noqa: BLE001 — P-01: catch every exception
                    err = f"{type(exc).__name__}: {str(exc)[:300]}"
                    await tracker.fail(err)
                    logger.warning(
                        "tools_node: tool %r raised: %s", name, err
                    )
                    out_messages.append(
                        ToolMessage(
                            content=f"Error from {name}: {err}",
                            tool_call_id=call_id,
                            name=name,
                        )
                    )

    return {"messages": out_messages}
