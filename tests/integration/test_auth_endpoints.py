"""Integration tests for /api/v1/auth/* endpoints."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from app.core.security import create_refresh_token, hash_password
from app.models.user import User
from tests.conftest import MockSession, _make_user
from tests.integration.conftest import _auth_headers, _make_db_user


class TestRegister:
    async def test_register_new_user_returns_201(self, client, mock_db):
        """Registering a brand-new email and merchant_id returns 201 with user data."""
        # Both duplicate-checks return None → user does not exist
        mock_db.set_default(scalar=None)

        resp = await client.post("/api/v1/auth/register", json={
            "email": "new@example.com",
            "password": "SecurePass1!",
            "merchant_id": "new-merchant",
            "role": "merchant",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["email"] == "new@example.com"
        assert data["merchant_id"] == "new-merchant"

    async def test_register_duplicate_email_returns_400(self, client, mock_db):
        """Registering with an already-used email returns 400 EMAIL_ALREADY_REGISTERED."""
        existing = _make_db_user()
        # First execute (email check) → returns existing user
        mock_db.push(scalar=existing)

        resp = await client.post("/api/v1/auth/register", json={
            "email": "existing@example.com",  # valid email matching existing user pattern
            "password": "SecurePass1!",
            "merchant_id": "brand-new-id",
        })
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "EMAIL_ALREADY_REGISTERED"

    async def test_register_duplicate_merchant_id_returns_400(self, client, mock_db):
        """Registering with an already-used merchant_id returns 400 MERCHANT_ID_ALREADY_TAKEN."""
        existing = _make_db_user()
        # Email check → None, merchant_id check → existing user
        mock_db.push(scalar=None)
        mock_db.push(scalar=existing)

        resp = await client.post("/api/v1/auth/register", json={
            "email": "fresh@example.com",
            "password": "SecurePass1!",
            "merchant_id": existing.merchant_id,
        })
        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "MERCHANT_ID_ALREADY_TAKEN"

    async def test_register_invalid_email_returns_422(self, client, mock_db):
        """An invalid email format must be rejected with HTTP 422."""
        resp = await client.post("/api/v1/auth/register", json={
            "email": "not-an-email",
            "password": "SecurePass1!",
            "merchant_id": "some-id",
        })
        assert resp.status_code == 422

    async def test_register_short_password_returns_422(self, client, mock_db):
        """A password shorter than 8 characters must be rejected with HTTP 422."""
        resp = await client.post("/api/v1/auth/register", json={
            "email": "ok@example.com",
            "password": "short",
            "merchant_id": "mid-abc",
        })
        assert resp.status_code == 422


class TestLogin:
    async def test_login_success_returns_tokens(self, client, mock_db):
        """Correct credentials return 200 with access_token and refresh_token."""
        password = "CorrectPass1!"
        user = _make_db_user(password=password)
        mock_db.push(scalar=user)

        resp = await client.post("/api/v1/auth/login", json={
            "email": user.email,
            "password": password,
        })
        assert resp.status_code == 200
        body = resp.json()
        assert "access_token" in body
        assert "refresh_token" in body

    async def test_login_wrong_password_returns_401(self, client, mock_db):
        """Wrong password returns 401 INVALID_CREDENTIALS."""
        user = _make_db_user(password="RealPass1!")
        mock_db.push(scalar=user)

        resp = await client.post("/api/v1/auth/login", json={
            "email": user.email,
            "password": "WrongPass1!",
        })
        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == "INVALID_CREDENTIALS"

    async def test_login_unknown_email_returns_401(self, client, mock_db):
        """Unknown email returns 401 INVALID_CREDENTIALS."""
        mock_db.push(scalar=None)
        resp = await client.post("/api/v1/auth/login", json={
            "email": "nobody@example.com",
            "password": "AnyPass1!",
        })
        assert resp.status_code == 401

    async def test_login_inactive_account_returns_401(self, client, mock_db):
        """Inactive account login returns 401 ACCOUNT_INACTIVE."""
        user = _make_db_user()
        user.is_active = False
        mock_db.push(scalar=user)

        resp = await client.post("/api/v1/auth/login", json={
            "email": user.email,
            "password": "Password1!",
        })
        assert resp.status_code == 401
        assert resp.json()["error"]["code"] == "ACCOUNT_INACTIVE"


class TestRefreshAndLogout:
    async def test_refresh_valid_token_returns_new_access_token(self, client):
        """A valid refresh token exchanges for a new access token."""
        user_id = str(uuid.uuid4())
        refresh = create_refresh_token(user_id)
        resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
        assert resp.status_code == 200
        assert "access_token" in resp.json()

    async def test_refresh_invalid_token_returns_401(self, client):
        """An invalid refresh token returns 401."""
        resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": "garbage.token.here"})
        assert resp.status_code == 401

    async def test_logout_with_valid_token_returns_200(self, client, mock_db):
        """Logout with a valid bearer token returns 200 with success message."""
        user = _make_db_user()
        mock_db.push(scalar=user)  # get_current_user DB lookup

        resp = await client.post(
            "/api/v1/auth/logout",
            json={"refresh_token": create_refresh_token(str(user.id))},
            headers={"Authorization": f"Bearer {create_refresh_token(str(user.id))}"},
        )
        # Logout uses get_current_user which expects an access token
        # Re-issue with access token
        from app.core.security import create_access_token
        mock_db.push(scalar=user)
        resp2 = await client.post(
            "/api/v1/auth/logout",
            json={"refresh_token": create_refresh_token(str(user.id))},
            headers={"Authorization": f"Bearer {create_access_token(str(user.id))}"},
        )
        assert resp2.status_code == 200
