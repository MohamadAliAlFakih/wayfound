"""Vector similarity retrieval for Wayfound RAG.

Strategy (per STATE.md Advanced RAG stack):
1. Embed the query using sentence-transformers/all-MiniLM-L6-v2 (384-dim).
2. Search child chunks by cosine distance (precision layer).
3. For each child hit, fetch its parent chunk (context layer).
4. Return deduplicated parent chunks ranked by child hit score.

This gives short, precise child matches while returning full-context parents
to the LLM — the standard parent-document retrieval pattern.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import select

from app.core.embeddings import LocalEmbedder
from app.db.engine import async_session_factory
from rag.models import Chunk

logger = logging.getLogger(__name__)


async def retrieve(
    query: str,
    top_k: int = 5,
    destination_filter: str | None = None,
    openai_client: LocalEmbedder | None = None,
) -> list[dict[str, Any]]:
    """Retrieve top_k parent chunks most relevant to query.

    Args:
        query: Natural-language query string.
        top_k: Number of parent chunks to return.
        destination_filter: Optional destination name to restrict search.
        openai_client: Injected client (used in tests). Reads OPENAI_API_KEY from env if None.

    Returns:
        List of dicts with keys: id, destination, section, content, score.
        Ordered by ascending cosine distance (lower = more similar).
    """
    client = openai_client or LocalEmbedder.load()
    query_vec = await client.embed_one(query)

    session_factory = async_session_factory()
    async with session_factory() as session:
        # Step 1: Find top child chunks by cosine distance.
        # Select Chunk + the cosine distance value so we can surface it in the API.
        distance_col = Chunk.embedding.cosine_distance(query_vec).label("distance")
        child_q = (
            select(Chunk, distance_col)
            .where(Chunk.parent_id.isnot(None))
            .order_by(distance_col)
            .limit(top_k * 3)  # over-fetch; deduplication will reduce to top_k parents
        )
        if destination_filter:
            child_q = child_q.where(Chunk.destination == destination_filter)

        child_rows = (await session.execute(child_q)).all()

        if not child_rows:
            logger.warning("retrieve: no child chunks found for query %r", query[:80])
            return []

        # Step 2: Collect unique parent IDs in hit order, tracking the BEST
        # (smallest) child distance per parent.
        first_distance_for_parent: dict[uuid.UUID, float] = {}
        ordered_parent_ids: list[uuid.UUID] = []
        for child, distance in child_rows:
            pid = child.parent_id
            if pid not in first_distance_for_parent:
                first_distance_for_parent[pid] = float(distance)
                ordered_parent_ids.append(pid)
            if len(ordered_parent_ids) >= top_k:
                break

        # Step 3: Fetch parent chunks
        parent_q = select(Chunk).where(Chunk.id.in_(ordered_parent_ids))
        parent_result = await session.execute(parent_q)
        parents_by_id = {p.id: p for p in parent_result.scalars().all()}

        # Step 4: Return in hit order with both rank and raw cosine distance
        results: list[dict[str, Any]] = []
        for i, pid in enumerate(ordered_parent_ids):
            parent = parents_by_id.get(pid)
            if parent:
                results.append(
                    {
                        "id": str(parent.id),
                        "destination": parent.destination,
                        "section": parent.section,
                        "content": parent.content,
                        "score": i,  # rank position (0 = closest child match)
                        "distance": round(first_distance_for_parent[pid], 4),
                    }
                )

        logger.info(
            "retrieve %r -> %d parents (%s)",
            query[:60],
            len(results),
            [r["destination"] for r in results],
        )
        return results
