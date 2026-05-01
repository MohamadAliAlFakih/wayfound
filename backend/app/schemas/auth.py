"""Auth request/response schemas.

D-03: register accepts username + email + password; both username and email unique.
D-04: login accepts email + password (username is for display only).
D-05: password Field(min_length=8) only — no regex, no max length.
OQ-3: bcrypt silently truncates to 72 bytes; documented in OpenAPI description.
Email is lowercased at the schema layer (single source of truth — see RESEARCH 5).
"""
from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field, field_validator


class RegisterRequest(BaseModel):
    """POST /auth/register request body."""

    username: str = Field(
        min_length=3,
        max_length=64,
        pattern=r"^[a-zA-Z0-9_-]+$",
        description="3-64 chars; letters, digits, underscore, hyphen.",
    )
    email: EmailStr = Field(
        description="Email address. Stored lowercased.",
    )
    password: str = Field(
        min_length=8,
        description=(
            "Password (min 8 chars). Bcrypt silently truncates inputs longer "
            "than 72 bytes — only the first 72 bytes affect the hash."
        ),
    )

    @field_validator("email")
    @classmethod
    def lowercase_email(cls, v: str) -> str:
        return v.lower()


class LoginRequest(BaseModel):
    """POST /auth/login request body. Login key is email (D-04)."""

    email: EmailStr
    password: str

    @field_validator("email")
    @classmethod
    def lowercase_email(cls, v: str) -> str:
        return v.lower()


class TokenResponse(BaseModel):
    """POST /auth/login response body (D-07)."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds; equals JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60
