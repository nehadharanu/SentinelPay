"""Integration-test fixtures: FastAPI AsyncClient with all external I/O mocked."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

import app.dependencies as deps
from app.core.security import create_access_token, hash_password
from app.db.session import get_db
from app.dependencies import get_redis
from app.main import app
from tests.conftest import MockSession, _make_user


def _make_db_user(role="merchant", merchant_id="test-merchant", password="Password1!"):
    user = _make_user(role, merchant_id)
    user.hashed_password = hash_password(password)
    return user


def _token_for(user) -> str:
    return create_access_token(str(user.id))


def _auth_headers(user) -> dict:
    return {"Authorization": f"Bearer {_token_for(user)}"}


@pytest.fixture
def mock_db():
    return MockSession()


@pytest.fixture
async def client(mock_db, mock_redis):
    """AsyncClient targeting the FastAPI app with DB and Redis fully mocked."""
    deps._redis_client = mock_redis

    async def override_db():
        yield mock_db

    with patch("app.main.init_db", new=AsyncMock()):
        app.dependency_overrides[get_db] = override_db
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as c:
            yield c

    app.dependency_overrides.clear()
    deps._redis_client = None
