import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, field_validator


class RegisterRequest(BaseModel):
    """Request body for POST /auth/register."""

    email: EmailStr
    password: str
    merchant_id: str
    role: str = "merchant"

    @field_validator("password")
    @classmethod
    def password_min_length(cls, v: str) -> str:
        """Ensure password is at least 8 characters."""
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters.")
        return v

    @field_validator("merchant_id")
    @classmethod
    def merchant_id_format(cls, v: str) -> str:
        """Ensure merchant_id is 3–50 alphanumeric characters or dashes."""
        import re
        if not re.match(r"^[a-zA-Z0-9\-]{3,50}$", v):
            raise ValueError("merchant_id must be 3–50 alphanumeric characters or dashes.")
        return v

    @field_validator("role")
    @classmethod
    def role_valid(cls, v: str) -> str:
        """Ensure role is merchant or admin."""
        if v not in ("merchant", "admin"):
            raise ValueError("role must be 'merchant' or 'admin'.")
        return v


class UserResponse(BaseModel):
    """Response schema representing a user."""

    id: uuid.UUID
    email: str
    merchant_id: str
    role: str
    is_active: bool
    created_at: datetime
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class LoginRequest(BaseModel):
    """Request body for POST /auth/login."""

    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    """Response schema for successful authentication."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class AccessTokenResponse(BaseModel):
    """Response schema for token refresh."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshRequest(BaseModel):
    """Request body for POST /auth/refresh."""

    refresh_token: str


class LogoutRequest(BaseModel):
    """Request body for POST /auth/logout."""

    refresh_token: str
