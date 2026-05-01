"""Authentication primitives: password hashing, JWT issue/decode, current user dep.

D-01: HS256 + python-jose; 60-min access TTL.
D-02: No refresh token (single access token).
D-04: /auth/login uses email; this module accepts UUID `sub`.
D-05: Password length policy is enforced by Pydantic schemas, not here.
D-06: passlib CryptContext with deprecated="auto", default cost factor.
P-03: bcrypt pinned to 4.0.1 in pyproject.toml.
P-04: catch JWTError (base) + ValueError (UUID parse); single 401 path.
P-05: always settings.jwt_secret_key.get_secret_value() — never str(...).
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import settings
from app.db.engine import get_db_session

logger = logging.getLogger(__name__)

# D-06: passlib CryptContext with bcrypt, deprecated="auto", default cost factor.
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# HTTP Bearer scheme — Swagger renders a simple "paste token" Authorize field.
bearer_scheme = HTTPBearer()


def hash_password(plain: str) -> str:
    """Hash a plaintext password with bcrypt (cost factor 12).

    bcrypt silently truncates inputs longer than 72 bytes (D-05; OQ-3) — this
    is documented in the OpenAPI schema for /auth/register, not enforced here.
    """
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Constant-time verify a plaintext password against a bcrypt hash."""
    return pwd_context.verify(plain, hashed)


def create_access_token(user_id: UUID) -> str:
    """Issue an HS256 JWT with sub=user_id and a `jwt_access_token_expire_minutes` exp.

    P-05: always pass the unwrapped secret to jwt.encode; never str(SecretStr).
    """
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_access_token_expire_minutes),
    }
    return jwt.encode(
        payload,
        settings.jwt_secret_key.get_secret_value(),
        algorithm=settings.jwt_algorithm,
    )


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
):
    """FastAPI dependency that resolves the current user from a Bearer token.

    Raises 401 with `WWW-Authenticate: Bearer` on any failure (P-04).
    Logs the underlying JWT error server-side at INFO; never returns it to the
    client (D-09 — generic detail; no info leakage).
    """
    token = credentials.credentials
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    # Lazy import to avoid Wave 1/Wave 2 cycle; User is created in plan 03-03.
    from app.models.user import User  # noqa: PLC0415

    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key.get_secret_value(),
            algorithms=[settings.jwt_algorithm],
        )
        sub = payload.get("sub")
        if sub is None:
            raise credentials_exc
        user_id = UUID(sub)
    except (JWTError, ValueError) as e:
        logger.info("jwt decode failed: %s", e)
        raise credentials_exc

    user = await session.get(User, user_id)
    if user is None:
        raise credentials_exc
    return user
