"""Stdlib logging configuration for the Wayfound backend.

D-22: no print() anywhere in the backend.
D-23: plain stdlib format `%(asctime)s %(levelname)s %(name)s %(message)s` at INFO.
      JSON formatter is deferred to Phase 6.
"""
from __future__ import annotations

import logging


def configure_logging() -> None:
    """Configure stdlib logging once at app startup.

    Called from app/main.py before the lifespan handler runs. `force=True`
    so calling this twice (e.g., in tests) does not stack handlers.
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        force=True,
    )
