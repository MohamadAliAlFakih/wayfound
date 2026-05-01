"""Async SQLAlchemy engine, session factory, and FastAPI session dependency.

IMPORTANT — pgvector ordering (STATE.md, P-07):
    `pgvector.sqlalchemy` MUST be imported at module level BEFORE any SQLAlchemy
    async engine is created. Importing afterwards causes UndefinedObject errors
    at vector-column query time.
"""
from __future__ import annotations

import logging
from typing import AsyncIterator

# pgvector type registration MUST come before sqlalchemy.ext.asyncio (STATE.md lock)
import pgvector.sqlalchemy  # noqa: F401  — side-effect import, do not remove
from fastapi import Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.db.base import Base

logger = logging.getLogger(__name__)

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """Return the module-level async engine, creating it on first call.

    Reads DATABASE_URL via the Settings singleton (D-17 — no os.getenv
    outside settings). Settings is imported lazily to avoid an import
    cycle when this module is reached before settings is initialized
    (e.g., during Alembic offline mode).
    """
    global _engine
    if _engine is None:
        from app.core.settings import settings  # local import — D-17 + cycle avoidance

        _engine = create_async_engine(str(settings.database_url), echo=False)
    return _engine


def async_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the module-level async session factory.

    expire_on_commit=False so ORM attributes remain accessible after commit
    (Phase 2 carry-over decision).
    """
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            get_engine(), class_=AsyncSession, expire_on_commit=False
        )
    return _session_factory


def build_engine_and_factory(
    url: str,
) -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
    """Build a fresh engine + factory bound to `url`.

    Use this in app/main.py lifespan so the lifespan can dispose the engine
    explicitly at shutdown. Module-level get_engine()/async_session_factory()
    are kept for backward compatibility with rag/ingest.py and rag/retrieval.py
    (script-mode usage).
    """
    engine = create_async_engine(url, echo=False)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return engine, factory


async def create_tables() -> None:
    """Phase 2 dev convenience — kept for tests and `python -m rag.ingest`.

    Production schema is owned by Alembic (D-12, D-13). This helper is no
    longer used in the FastAPI lifespan.
    """
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)
    logger.info("RAG tables ready (dev create_tables path)")


async def get_db_session(request: Request) -> AsyncIterator[AsyncSession]:
    """FastAPI dependency that yields a fresh AsyncSession per request.

    Reads the lifespan-bound factory off `request.app.state.db_session_factory`.
    Routes that mutate must call `await session.commit()` explicitly (P-08).
    """
    factory: async_sessionmaker[AsyncSession] = request.app.state.db_session_factory
    async with factory() as session:
        yield session
