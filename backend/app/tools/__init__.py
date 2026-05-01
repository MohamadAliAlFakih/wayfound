"""Phase 4 tool aggregator and re-exports.

`build_all_tools(app_state)` returns the 5-tool list used to bind_tools(...)
on the agent_llm in lifespan (D-05). Tool factories accept dependencies via
closures (D-30 layout):

  - rag_tool:        embed_client (lifespan singleton, may be None)
  - classifier_tool: ml_model     (lifespan singleton, REQUIRED)
  - weather_tool:    none (reads settings at call time)
  - flights_tool:    none (reads settings at call time)
  - fx_tool:         none (reads settings at call time)

Bare aliases (`rag_tool`, `classifier_tool`) point at the factories and are
preserved from Plan 04-02 — they satisfy the Plan 04-02 success-criterion
import line `from app.tools import rag_tool, classifier_tool, ToolCallTracker`.
"""
from __future__ import annotations

from typing import Any

from app.tools.classifier import ClassifierToolInput, make_classifier_tool
from app.tools.fx import FXToolInput, make_fx_tool
from app.tools.rag import RAGToolInput, make_rag_tool
from app.tools.tracker import ToolCallTracker
from app.tools.weather import WeatherToolInput, make_weather_tool

# Bare aliases — preserved from Plan 04-02 success-criterion contract.
rag_tool = make_rag_tool
classifier_tool = make_classifier_tool


def build_all_tools(app_state: Any) -> list:
    """Build the 5-tool list (D-05). Caller is FastAPI lifespan.

    Args:
        app_state: FastAPI application state. Must expose `ml_model`
            (sklearn Pipeline) and `embed_client` (AsyncOpenAI | None).

    Returns:
        Ordered list of 5 StructuredTool instances suitable for
        `agent_llm.bind_tools(tools)` and the custom tools_node's
        `tool_map = {t.name: t for t in tools}`.
    """
    return [
        make_rag_tool(getattr(app_state, "embed_client", None)),
        make_classifier_tool(app_state.ml_model),
        make_weather_tool(),
        make_fx_tool(),
    ]


__all__ = [
    "ClassifierToolInput",
    "FXToolInput",
    "RAGToolInput",
    "ToolCallTracker",
    "WeatherToolInput",
    "build_all_tools",
    "classifier_tool",
    "make_classifier_tool",
    "make_fx_tool",
    "make_rag_tool",
    "make_weather_tool",
    "rag_tool",
]
