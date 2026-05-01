"""FastAPI application entry point.

Lifespan singletons (Phase 3 + Phase 4):
  - DB engine + async session factory  — REQUIRED, fail-fast (Phase 3)
  - ML classifier (joblib)             — REQUIRED, fail-fast (Phase 3)
  - OpenAI AsyncOpenAI                 — OPTIONAL (Phase 3)
  - LangSmith env vars (D-27)          — OPTIONAL, set BEFORE ChatGroq (P-05)
  - ChatGroq extraction_llm (8b)       — REQUIRED in Phase 4 (D-01)
  - ChatGroq agent_llm (70b, bind_tools) — REQUIRED in Phase 4 (D-01)
  - 5 tools list (rag, classifier, weather, flights, fx) — REQUIRED (D-05)
  - Compiled StateGraph                — REQUIRED (build_graph(), §12)
  - background_tasks: set[asyncio.Task] — REQUIRED (P-02 fire-and-forget)

Run:
  cd backend && uv run uvicorn app.main:app --reload --port 8000
"""
from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

import joblib
from fastapi import FastAPI
from langchain_groq import ChatGroq
from openai import AsyncOpenAI

from app.agents.graph import build_graph
from app.core.logging import configure_logging
from app.core.settings import settings
from app.db.engine import build_engine_and_factory
from app.routes.auth import router as auth_router
from app.routes.health import router as health_router
from app.routes.trips import router as trips_router
from app.routes.users import router as users_router
from app.tools import build_all_tools

# Configure stdlib logging before lifespan runs (D-22, D-23, D-29).
configure_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Construct singletons before yielding, dispose them after.

    Path resolution for ML model: this file is `backend/app/main.py`, so
    `Path(__file__).resolve().parents[2]` is the project root containing
    `models/travel_classifier.joblib` (Phase 1 artifact).
    """
    # 1. DB engine + session factory — REQUIRED (Phase 3).
    engine, session_factory = build_engine_and_factory(str(settings.database_url))
    app.state.db_engine = engine
    app.state.db_session_factory = session_factory
    logger.info("DB engine constructed for %s", settings.database_url.hosts()[0]["host"])

    # 2. ML classifier — REQUIRED (Phase 1 artifact; classifier_tool depends on it).
    model_path = Path(__file__).resolve().parents[2] / "models" / "travel_classifier.joblib"
    if not model_path.exists():
        # Fail fast: Phase 4 routes cannot work without this. Better to crash on
        # startup than 500 on every request.
        raise RuntimeError(
            f"ML classifier not found at {model_path}; run Phase 1 to produce it."
        )
    app.state.ml_model = joblib.load(model_path)
    logger.info("ML classifier loaded from %s", model_path)

    # 3. Local embedding model (sentence-transformers/all-MiniLM-L6-v2, 384-dim).
    from app.core.embeddings import LocalEmbedder
    app.state.embed_client = LocalEmbedder.load()

    # 4. LangSmith env vars (D-27 + P-05) — set BEFORE constructing the LLM clients.
    # NOTE: D-27 documents this as the ONLY allowed os.environ write outside
    # core/settings.py. Reason: LangChain SDK reads LANGCHAIN_TRACING_V2 at
    # Runnable construction; setting it after the first chat-model is built means
    # traces silently go nowhere (P-05 / RESEARCH §13).
    if settings.langsmith_api_key is not None:
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        os.environ["LANGCHAIN_API_KEY"] = settings.langsmith_api_key.get_secret_value()
        os.environ["LANGCHAIN_PROJECT"] = "wayfound"
        logger.info("LangSmith tracing enabled (project=wayfound)")
    else:
        logger.info("LANGSMITH_API_KEY not set — tracing disabled (D-27)")

    # 5. ChatGroq instances (D-01) — REQUIRED. Fail-fast if key missing
    # (no fallback per RESEARCH §Environment Availability).
    if settings.groq_api_key is None:
        raise RuntimeError(
            "GROQ_API_KEY required for Phase 4 — set it in .env (no fallback)."
        )
    groq_key = settings.groq_api_key.get_secret_value()
    app.state.extraction_llm = ChatGroq(
        model="llama-3.1-8b-instant",
        temperature=0,
        api_key=groq_key,
        timeout=30,
        max_retries=2,
    )

    # 6. Build the 5 tools (D-05) and bind them to the 70b agent LLM.
    tools = build_all_tools(app.state)
    app.state.agent_tools = tools  # plan_trip reads this to build tools_map
    app.state.agent_llm = ChatGroq(
        model="llama-3.3-70b-versatile",
        temperature=0.2,
        api_key=groq_key,
        timeout=60,
        max_retries=2,
    ).bind_tools(tools)
    logger.info(
        "ChatGroq instances constructed: extraction=8b agent=70b tools=%d",
        len(tools),
    )

    # 7. Compile graph once (RESEARCH §12 — compile is expensive, ainvoke is cheap).
    app.state.graph = build_graph()
    logger.info("LangGraph compiled with %d-tool agent", len(tools))

    # 8. Background-task set (P-02) — strong references for fire-and-forget webhooks.
    app.state.background_tasks = set()
    logger.info("background_tasks set initialized for fire-and-forget webhooks")

    yield  # ----- app runs here -----

    # Shutdown — cancel any in-flight webhook tasks, then dispose DB engine.
    pending: set[asyncio.Task] = set(app.state.background_tasks or set())
    for task in pending:
        task.cancel()
    if pending:
        # Wait briefly for cancellations to settle (max ~1s)
        try:
            await asyncio.wait(pending, timeout=1.0)
        except Exception as exc:  # noqa: BLE001
            logger.warning("background task cancellation error: %s", exc)
    await engine.dispose()
    logger.info("DB engine disposed; %d background tasks cancelled", len(pending))


app = FastAPI(
    title="Wayfound API",
    description="Phase 4 backend — auth + agent + Discord webhook.",
    version="0.4.0",
    lifespan=lifespan,
)

# Mount routers (Phase 3 + Phase 4).
app.include_router(health_router)
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(trips_router)
