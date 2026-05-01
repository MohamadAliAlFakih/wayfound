"""GET /health — liveness probe (no DB hit per D-07)."""
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health", status_code=200)
async def health() -> dict[str, str]:
    """Return 200 with a static body. No DB probe (D-07)."""
    return {"status": "ok"}
