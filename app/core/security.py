from datetime import datetime, timedelta, timezone
from typing import Literal

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.config import settings
from app.core.exceptions import InvalidToken, TokenExpired, InvalidRefreshToken, RefreshTokenExpired

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

ALGORITHM = "HS256"


def hash_password(plain: str) -> str:
    """Return the bcrypt hash of a plaintext password."""
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Return True if plain matches hashed, False otherwise."""
    return pwd_context.verify(plain, hashed)


def _create_token(
    subject: str,
    token_type: Literal["access", "refresh"],
    expires_delta: timedelta,
) -> str:
    """Encode a signed JWT with subject, type, and expiry claims."""
    expire = datetime.now(timezone.utc) + expires_delta
    payload = {"sub": subject, "type": token_type, "exp": expire}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM)


def create_access_token(user_id: str) -> str:
    """Create a short-lived access JWT for the given user UUID."""
    return _create_token(
        user_id,
        "access",
        timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )


def create_refresh_token(user_id: str) -> str:
    """Create a long-lived refresh JWT for the given user UUID."""
    return _create_token(
        user_id,
        "refresh",
        timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )


def decode_access_token(token: str) -> str:
    """Decode an access token and return the user UUID subject.

    Raises InvalidToken or TokenExpired on failure.
    """
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "access":
            raise InvalidToken()
        return payload["sub"]
    except JWTError as exc:
        if "expired" in str(exc).lower():
            raise TokenExpired()
        raise InvalidToken()


def decode_refresh_token(token: str) -> str:
    """Decode a refresh token and return the user UUID subject.

    Raises InvalidRefreshToken or RefreshTokenExpired on failure.
    """
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("type") != "refresh":
            raise InvalidRefreshToken()
        return payload["sub"]
    except JWTError as exc:
        if "expired" in str(exc).lower():
            raise RefreshTokenExpired()
        raise InvalidRefreshToken()
