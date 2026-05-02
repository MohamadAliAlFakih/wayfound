"""rag_tool — Phase 2 retrieval wrapped as a LangChain tool (D-09).

Factory pattern: `make_rag_tool(embed_client)` returns a `StructuredTool`
wrapping an async function with closure over the OpenAI embed client.
The tool body delegates to backend/rag/retrieval.py::retrieve(...) and
returns its list-of-dicts result unchanged.

The Phase 2 retrieve() opens its own AsyncSession internally via
`async_session_factory()` from app.db.engine, so this tool does NOT
accept a session — keeping the tool side-effect-free from a persistence
standpoint (ToolCallTracker handles the per-call audit trail).
"""
from __future__ import annotations

import logging
from typing import Any

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.core.embeddings import LocalEmbedder
from rag.retrieval import retrieve

logger = logging.getLogger(__name__)


class RAGToolInput(BaseModel):
    """D-09: flat schema for rag_tool."""

    query: str = Field(min_length=1, description="Natural-language query for retrieval.")
    destination_filter: str | None = Field(
        default=None,
        description="Optional destination name to restrict search (e.g. 'Reykjavik').",
    )


def make_rag_tool(embed_client: LocalEmbedder | None) -> StructuredTool:
    """Build the rag_tool with an injected OpenAI embed client (lifespan singleton).

    If `embed_client` is None (no OPENAI_API_KEY), the tool returns an empty
    list instead of crashing — matches Phase 2 'best-effort' behaviour.
    """

    async def _rag(
        query: str,
        destination_filter: str | None = None,
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        if embed_client is None:
            logger.warning("rag_tool: embed_client is None — returning empty result")
            return []
        results = await retrieve(
            query=query,
            top_k=top_k,
            destination_filter=destination_filter,
            openai_client=embed_client,
        )
        # Trim each chunk's content to 300 chars before returning. Cuts ~70%
        # of the token cost when these results get re-sent across agent turns.
        # The full text was already used at retrieval time; the LLM only needs
        # the gist for synthesis.
        max_content_chars = 300
        for r in results:
            content = r.get("content")
            if isinstance(content, str) and len(content) > max_content_chars:
                r["content"] = content[:max_content_chars].rstrip() + "…"

        logger.info(
            "rag_tool returned %d parents (trimmed to %d chars) for query=%r",
            len(results),
            max_content_chars,
            query[:60],
        )
        return results

    return StructuredTool.from_function(
        coroutine=_rag,
        name="rag_tool",
        description=(
            "Retrieve destination knowledge from Wikivoyage via pgvector similarity search. "
            "Returns a ranked list of parent chunks (id, destination, section, content, score). "
            "Use for questions about specific places, attractions, history, or culture."
        ),
        args_schema=RAGToolInput,
    )
