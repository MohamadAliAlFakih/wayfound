"""POST /auth/register and POST /auth/login (D-07)."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token
from app.core.settings import settings
from app.db.engine import get_db_session
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse
from app.schemas.user import RegisterResponse
from app.services.auth import authenticate_user, register_user

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    response_model=RegisterResponse,
    responses={
        409: {"description": "Username or email already taken"},
    },
)
async def register(
    payload: RegisterRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> RegisterResponse:
    """Create a new user. Returns 201 with {user_id, username, email}."""
    user = await register_user(
        session,
        username=payload.username,
        email=payload.email,
        password=payload.password,
    )
    return RegisterResponse(
        user_id=user.id,
        username=user.username,
        email=user.email,
    )


@router.post(
    "/login",
    status_code=status.HTTP_200_OK,
    response_model=TokenResponse,
    responses={401: {"description": "Invalid credentials"}},
)
async def login(
    payload: LoginRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> TokenResponse:
    """Validate credentials, issue a JWT access token (60-min TTL per D-01)."""
    user = await authenticate_user(
        session,
        email=payload.email,
        password=payload.password,
    )
    token = create_access_token(user.id)
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=settings.jwt_access_token_expire_minutes * 60,
    )
