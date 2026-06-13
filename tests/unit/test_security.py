"""Unit tests for app.core.security — JWT and password utilities."""

import time
from datetime import timedelta

import pytest
from jose import jwt

from app.config import settings
from app.core.exceptions import InvalidRefreshToken, InvalidToken, RefreshTokenExpired, TokenExpired
from app.core.security import (
    ALGORITHM,
    _create_token,
    create_access_token,
    create_refresh_token,
    decode_access_token,
    decode_refresh_token,
    hash_password,
    verify_password,
)


class TestPasswordHashing:
    def test_hash_differs_from_plaintext(self):
        """Hashed password must not equal the original plaintext."""
        plain = "supersecret99"
        assert hash_password(plain) != plain

    def test_verify_correct_password_returns_true(self):
        """verify_password returns True when the plain text matches the hash."""
        plain = "mysecretpass"
        assert verify_password(plain, hash_password(plain)) is True

    def test_verify_wrong_password_returns_false(self):
        """verify_password returns False when the plain text does not match."""
        assert verify_password("wrong", hash_password("correct")) is False


class TestAccessTokens:
    def test_create_and_decode_access_token(self):
        """A freshly created access token decodes back to the original user ID."""
        user_id = "abc-123-user-id"
        token = create_access_token(user_id)
        assert decode_access_token(token) == user_id

    def test_expired_access_token_raises(self):
        """An access token past its expiry raises TokenExpired."""
        token = _create_token("uid", "access", timedelta(seconds=-1))
        with pytest.raises(TokenExpired):
            decode_access_token(token)

    def test_wrong_type_access_token_raises(self):
        """A refresh token passed to decode_access_token raises InvalidToken."""
        token = create_refresh_token("uid")
        with pytest.raises(InvalidToken):
            decode_access_token(token)

    def test_garbage_token_raises_invalid(self):
        """A random string passed as token raises InvalidToken."""
        with pytest.raises(InvalidToken):
            decode_access_token("not.a.jwt")


class TestRefreshTokens:
    def test_create_and_decode_refresh_token(self):
        """A freshly created refresh token decodes back to the original user ID."""
        user_id = "user-xyz-789"
        token = create_refresh_token(user_id)
        assert decode_refresh_token(token) == user_id

    def test_expired_refresh_token_raises(self):
        """An expired refresh token raises RefreshTokenExpired."""
        token = _create_token("uid", "refresh", timedelta(seconds=-1))
        with pytest.raises(RefreshTokenExpired):
            decode_refresh_token(token)

    def test_wrong_type_refresh_token_raises(self):
        """An access token passed to decode_refresh_token raises InvalidRefreshToken."""
        token = create_access_token("uid")
        with pytest.raises(InvalidRefreshToken):
            decode_refresh_token(token)
