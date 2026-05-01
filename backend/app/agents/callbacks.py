"""TokenAccumulator AsyncCallbackHandler — aggregates token usage + cost (D-28).

Pass via config={"callbacks": [accumulator], ...} on graph.ainvoke.
After the run, read accumulator.prompt_tokens / completion_tokens / total_cost_usd.

Phase 6 reads representative values for the README cost table (AGT-07).

ChatGroq emits `usage_metadata` on every AIMessage when stream_usage=True
(D-01). This handler reads it from on_llm_end's LLMResult and aggregates.
"""
from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.outputs import LLMResult

from app.core.pricing import compute_cost_usd

logger = logging.getLogger(__name__)


class TokenAccumulator(AsyncCallbackHandler):
    """Async callback handler that sums per-LLM-call token usage and cost.

    Read prompt_tokens / completion_tokens / total_tokens / total_cost_usd
    AFTER graph.ainvoke returns. `per_call` exposes per-LLM-call breakdown.
    """

    def __init__(self) -> None:
        self.prompt_tokens: int = 0
        self.completion_tokens: int = 0
        self.total_cost_usd: float = 0.0
        self.per_call: list[dict[str, Any]] = []

    @property
    def total_tokens(self) -> int:
        """Convenience for Discord embed footer (Plan 04-05)."""
        return self.prompt_tokens + self.completion_tokens

    async def on_llm_end(
        self,
        response: LLMResult,
        *,
        run_id: UUID,
        parent_run_id: UUID | None = None,
        tags: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        """Extract token_usage from response.llm_output OR from message.usage_metadata."""
        usage: dict[str, int] | None = None
        model_name: str | None = None
        llm_output = getattr(response, "llm_output", None) or {}
        if isinstance(llm_output, dict):
            model_name = llm_output.get("model_name") or llm_output.get("model")
            token_usage = llm_output.get("token_usage")
            if isinstance(token_usage, dict):
                usage = {
                    "prompt_tokens": int(token_usage.get("prompt_tokens", 0) or 0),
                    "completion_tokens": int(
                        token_usage.get("completion_tokens", 0) or 0
                    ),
                }

        # Fallback: dig into generations[0][0].message.usage_metadata
        if usage is None:
            try:
                msg = response.generations[0][0].message  # type: ignore[attr-defined]
                meta = getattr(msg, "usage_metadata", None) or {}
                if meta:
                    usage = {
                        "prompt_tokens": int(meta.get("input_tokens", 0) or 0),
                        "completion_tokens": int(meta.get("output_tokens", 0) or 0),
                    }
                if model_name is None:
                    response_meta = getattr(msg, "response_metadata", None) or {}
                    if isinstance(response_meta, dict):
                        model_name = response_meta.get("model_name") or response_meta.get(
                            "model"
                        )
            except (AttributeError, IndexError, KeyError, TypeError):
                pass

        if usage is None:
            logger.debug(
                "TokenAccumulator: no usage on this on_llm_end event (run_id=%s)",
                run_id,
            )
            return

        self.prompt_tokens += usage["prompt_tokens"]
        self.completion_tokens += usage["completion_tokens"]
        cost = compute_cost_usd(model_name or "", usage)
        self.total_cost_usd += cost
        self.per_call.append(
            {"model": model_name or "unknown", "cost_usd": cost, **usage}
        )
        logger.info(
            "token_usage model=%s prompt=%d completion=%d cost_usd=%.6f",
            model_name,
            usage["prompt_tokens"],
            usage["completion_tokens"],
            cost,
        )
