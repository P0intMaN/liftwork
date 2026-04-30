"""POST /auth/login — exchange email+password for a JWT."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from liftwork_api.auth import CurrentUser
from liftwork_api.dependencies import get_db, get_settings_dep
from liftwork_api.schemas import CurrentUser as CurrentUserSchema
from liftwork_api.schemas import LoginRequest, TokenResponse
from liftwork_core.config import Settings
from liftwork_core.repositories import UserRepository
from liftwork_core.security import issue_jwt, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    session: Annotated[AsyncSession, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings_dep)],
) -> TokenResponse:
    user = await UserRepository(session).get_by_email(body.email)
    pw = body.password.get_secret_value()
    if user is None or not verify_password(pw, user.password_hash):
        # Constant-ish response time for both branches keeps timing attacks weak.
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="account is disabled")

    token = issue_jwt(
        subject=str(user.id),
        settings=settings.jwt,
        claims={"role": user.role.value},
    )
    return TokenResponse(
        access_token=token,
        expires_in=settings.jwt.ttl_seconds,
    )


@router.get("/me", response_model=CurrentUserSchema)
async def me(user: CurrentUser) -> CurrentUserSchema:
    return CurrentUserSchema.model_validate(user)
