import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    AccountInactive,
    EmailAlreadyRegistered,
    InvalidCredentials,
    InvalidRefreshToken,
    MerchantIdAlreadyTaken,
)
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    hash_password,
    verify_password,
)
from app.db.session import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.auth import (
    AccessTokenResponse,
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)

router = APIRouter()


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    body: RegisterRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    """Register a new user account and return the created user record."""
    existing_email = await db.execute(select(User).where(User.email == body.email))
    if existing_email.scalar_one_or_none():
        raise EmailAlreadyRegistered()

    existing_mid = await db.execute(
        select(User).where(User.merchant_id == body.merchant_id)
    )
    if existing_mid.scalar_one_or_none():
        raise MerchantIdAlreadyTaken()

    user = User(
        id=uuid.uuid4(),
        email=body.email,
        hashed_password=hash_password(body.password),
        merchant_id=body.merchant_id,
        role=body.role,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
    """Authenticate and return access + refresh JWT tokens."""
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()

    if not user or not verify_password(body.password, user.hashed_password):
        raise InvalidCredentials()
    if not user.is_active:
        raise AccountInactive()

    return TokenResponse(
        access_token=create_access_token(str(user.id)),
        refresh_token=create_refresh_token(str(user.id)),
        expires_in=1800,
    )


@router.post("/refresh", response_model=AccessTokenResponse)
async def refresh(body: RefreshRequest) -> AccessTokenResponse:
    """Exchange a valid refresh token for a new access token."""
    user_id = decode_refresh_token(body.refresh_token)
    return AccessTokenResponse(
        access_token=create_access_token(user_id),
        expires_in=1800,
    )


@router.post("/logout")
async def logout(
    body: LogoutRequest,
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    """Invalidate the session by instructing the client to discard its tokens.

    Stateless JWT implementation; token is not server-side blacklisted.
    """
    return {"message": "Successfully logged out"}
