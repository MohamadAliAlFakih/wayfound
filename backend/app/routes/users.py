"""GET /me — protected via Depends(get_current_user) (D-07)."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.security import get_current_user
from app.models.user import User
from app.schemas.user import UserOut

router = APIRouter(tags=["users"])


@router.get(
    "/me",
    status_code=200,
    response_model=UserOut,
    responses={401: {"description": "Missing or invalid Bearer token"}},
)
async def me(current_user: Annotated[User, Depends(get_current_user)]) -> UserOut:
    """Return the authenticated user's profile."""
    return UserOut(
        user_id=current_user.id,
        username=current_user.username,
        email=current_user.email,
        created_at=current_user.created_at,
    )
