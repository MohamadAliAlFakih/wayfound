"""Compile the LangGraph agent (D-03, AGT-01, OQ-1).

Topology:
    START -> extraction -> llm  <->  tools  -> END
                          ^_______|
                      (when tool_calls present)

Conditional edge after llm_node: if last AIMessage has non-empty tool_calls,
route to tools_node; otherwise END.

`RECURSION_LIMIT = 20` — see deviation note below (OQ-1).
"""
from __future__ import annotations

from langgraph.graph import END, StateGraph

from app.agents.nodes import extraction_node, llm_node, tools_node
from app.agents.state import AgentState

# OQ-1 deviation from CONTEXT D-04 ("10 LLM iterations"):
# LangGraph's `recursion_limit` counts SUPER-STEPS (node transitions), and
# one Option-A loop iteration = llm_node (1) + tools_node (1) = 2 super-steps.
# To preserve the spec's "10 LLM iterations" intent, we set the limit to 20.
# See planning_context OQ-1 resolution.
RECURSION_LIMIT = 20


def _route_after_llm(state: AgentState) -> str:
    """Conditional edge: route to tools_node if last AIMessage has tool_calls,
    else END."""
    last = state["messages"][-1]
    tool_calls = getattr(last, "tool_calls", None)
    return "tools" if tool_calls else END


def build_graph() -> "object":  # CompiledStateGraph
    """Build and compile the LangGraph StateGraph.

    Returns a `CompiledStateGraph` (LangGraph type). Compile is the expensive
    step (~50-200ms); this function should be called ONCE in the FastAPI
    lifespan and the result stored on `app.state.graph`. Per-request usage
    is `await app.state.graph.ainvoke(state, config={...})`.

    Tools are NOT bound here — they are bound to the agent_llm in lifespan
    via `agent_llm.bind_tools(tools)`. The graph receives the bound LLM via
    `config["configurable"]["agent_llm"]` at invocation time.
    """
    g = StateGraph(AgentState)
    g.add_node("extraction", extraction_node)
    g.add_node("llm", llm_node)
    g.add_node("tools", tools_node)

    g.set_entry_point("extraction")
    g.add_edge("extraction", "llm")
    g.add_conditional_edges(
        "llm", _route_after_llm, {"tools": "tools", END: END}
    )
    g.add_edge("tools", "llm")

    return g.compile()
