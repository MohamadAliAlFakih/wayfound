"""Retrieval quality test for Wayfound RAG vector store.

Run with: cd backend && uv run python -m rag.test_retrieval

Requirements:
  - POSTGRES running with chunks table populated (>= 150 rows)
  - OPENAI_API_KEY and DATABASE_URL set in environment or .env

QUERY TEST RESULTS (fill in after running live — PASS/FAIL per query):
===========================================================================
  Q1 [tropical beaches, scuba diving, overwater bungalows]  -> Maldives   : ??
  Q2 [geisha districts, tea ceremonies, bamboo forests]     -> Kyoto       : ??
  Q3 [Eiffel Tower, croissants, Seine river]                -> Paris       : ??
  Q4 [Northern Lights, volcanoes, hot springs, geysers]     -> Reykjavik   : ??
  Q5 [ancient ruins, Colosseum, Vatican, pasta]             -> Rome        : ??
===========================================================================
Update ?? to PASS or FAIL after running the live test below.
"""
from __future__ import annotations

import asyncio
import logging
import os
from unittest.mock import AsyncMock, patch

from dotenv import load_dotenv

load_dotenv()

from .ingest import ensure_indexed
from .retrieval import retrieve

logger = logging.getLogger(__name__)

# 5 hand-written queries: (query, expected_destination, label)
QUERY_TESTS: list[tuple[str, str, str]] = [
    (
        "tropical beaches, scuba diving, overwater bungalows, crystal clear lagoons",
        "Maldives",
        "Q1",
    ),
    (
        "geisha districts, tea ceremonies, bamboo forests, zen temples",
        "Kyoto",
        "Q2",
    ),
    (
        "Eiffel Tower, croissants, Seine river, Louvre museum",
        "Paris",
        "Q3",
    ),
    (
        "Northern Lights, volcanoes, hot springs, geysers, midnight sun",
        "Reykjavik",
        "Q4",
    ),
    (
        "ancient ruins, Colosseum, Vatican, Roman Forum, pasta and pizza",
        "Rome",
        "Q5",
    ),
]


async def run_retrieval_tests() -> dict[str, bool]:
    """Run 5 query tests. Returns {label: passed} dict."""
    results: dict[str, bool] = {}
    for query, expected_dest, label in QUERY_TESTS:
        hits = await retrieve(query, top_k=3)
        destinations_returned = [h["destination"] for h in hits]
        passed = expected_dest in destinations_returned
        results[label] = passed
        status = "PASS" if passed else "FAIL"
        logger.info(
            "%s [%s] expected=%s got=%s -> %s",
            label,
            query[:50],
            expected_dest,
            destinations_returned,
            status,
        )
    return results


async def run_resilience_test() -> bool:
    """Test that ensure_indexed() does not raise when OpenAI is unreachable."""
    from openai import APIError
    import httpx

    fake_error = APIError(
        message="connection refused",
        request=httpx.Request("POST", "https://api.openai.com/v1/embeddings"),
        body=None,
    )

    with patch("rag.ingest.AsyncOpenAI") as mock_cls:
        mock_client = AsyncMock()
        mock_client.embeddings.create.side_effect = fake_error
        mock_cls.return_value = mock_client

        # Also patch create_tables to avoid needing a live DB for this test
        with patch("rag.ingest.create_tables", new_callable=AsyncMock):
            # Patch the session to report count=0 so ingest is attempted
            with patch("rag.ingest.async_session_factory") as mock_factory:
                mock_session = AsyncMock()
                mock_session.__aenter__ = AsyncMock(return_value=mock_session)
                mock_session.__aexit__ = AsyncMock(return_value=False)
                scalar_result = AsyncMock()
                scalar_result.scalar_one.return_value = 0
                mock_session.execute = AsyncMock(return_value=scalar_result)
                mock_factory.return_value.return_value = mock_session

                try:
                    await ensure_indexed()
                    logger.info("RESILIENCE PASS: ensure_indexed() completed without raising")
                    return True
                except Exception as exc:  # noqa: BLE001
                    logger.error("RESILIENCE FAIL: ensure_indexed() raised %s", exc)
                    return False


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    logger.info("=== Wayfound RAG Retrieval Tests ===")

    # Resilience test first (no live DB required)
    resilience_ok = await run_resilience_test()
    logger.info("Resilience test: %s", "PASS" if resilience_ok else "FAIL")

    # Live retrieval tests
    logger.info("Running 5 live retrieval queries ...")
    query_results = await run_retrieval_tests()

    passed = sum(query_results.values())
    total = len(query_results)
    logger.info(
        "=== Results: %d/%d PASS ===\n%s",
        passed,
        total,
        "\n".join(f"  {k}: {'PASS' if v else 'FAIL'}" for k, v in query_results.items()),
    )

    assert resilience_ok, "Resilience test failed"
    assert passed == total, f"Only {passed}/{total} retrieval queries passed"
    logger.info("ALL TESTS PASSED — Phase 2 success criteria 3 and 4 satisfied")


if __name__ == "__main__":
    asyncio.run(main())
