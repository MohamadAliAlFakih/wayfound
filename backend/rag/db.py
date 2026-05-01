"""Phase 2 compatibility shim — engine code now lives in app.db.engine.

Kept for backward compatibility with `python -m rag.ingest` and any test
fixtures that imported from here. New code should import from
`app.db.engine` directly (D-25).
"""
from app.db.engine import (  # noqa: F401
    async_session_factory,
    create_tables,
    get_engine,
)
