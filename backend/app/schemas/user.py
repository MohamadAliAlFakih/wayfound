"""User response schemas."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr


class UserOut(BaseModel):
    """GET /me response (D-07). Also used by /auth/register on 201."""

    model_config = ConfigDict(from_attributes=True)

    user_id: UUID
    username: str
    email: EmailStr
    created_at: datetime | None = None  # not returned by /auth/register


class RegisterResponse(BaseModel):
    """POST /auth/register response body (D-07 — subset of UserOut, no created_at)."""

    user_id: UUID
    username: str
    email: EmailStr
