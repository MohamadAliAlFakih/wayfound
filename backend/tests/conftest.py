"""Shared pytest fixtures + setup.

We make sure the env vars Settings() validates are present before the test
suite imports app code (Settings() runs at module import time).
"""
from __future__ import annotations

import os

# Set the four required env vars before anything imports app.core.settings.
os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test"
)
os.environ.setdefault(
    "JWT_SECRET_KEY", "test-secret-must-be-at-least-32-characters-long-yep"
)
os.environ.setdefault("JWT_ALGORITHM", "HS256")
os.environ.setdefault("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "60")
os.environ.setdefault("GROQ_API_KEY", "test-groq-key")