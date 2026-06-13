"""Shared pytest fixtures for SentinelPay test suite.

Environment variables are set before any app module is imported so that
pydantic-settings can find them during Settings() initialisation.
"""

import os
# Must precede all app imports — Settings() is called at module load time.
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-ant-test-key-thats-long-enough")
os.environ.setdefault("SECRET_KEY", "test-secret-key-that-is-at-least-32-characters-long!")

import types
import uuid
from collections import deque
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.schemas.transaction import TransactionCreate
from app.services.ai_scorer import AIResult
from app.services.behavioral_profiler import BehavioralResult
from app.services.rule_engine import RuleResult


# ---------------------------------------------------------------------------
# Mock DB helpers
# ---------------------------------------------------------------------------

class MockDBResult:
    """Mimics the cursor result returned by ``session.execute()``."""

    def __init__(self, scalar=None, scalars_list=None):
        self._scalar = scalar
        self._list = scalars_list

    def scalar_one_or_none(self):
        return self._scalar

    def scalar_one(self):
        return self._scalar

    def scalars(self):
        return self

    def all(self):
        if self._list is not None:
            return self._list
        return [self._scalar] if self._scalar is not None else []


class MockSession:
    """Async SQLAlchemy session mock with a configurable result queue."""

    def __init__(self):
        self._queue: deque = deque()
        self._default = MockDBResult(None)
        self.added = []
        self.deleted = []

    def push(self, scalar=None, scalars_list=None):
        """Enqueue a result to be returned by the next execute() call."""
        self._queue.append(MockDBResult(scalar, scalars_list))

    def set_default(self, scalar=None, scalars_list=None):
        """Set the fallback result returned when the queue is empty."""
        self._default = MockDBResult(scalar, scalars_list)

    async def execute(self, query):
        return self._queue.popleft() if self._queue else self._default

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        pass

    async def commit(self):
        pass

    async def refresh(self, obj):
        """Simulate DB refresh by applying server-side defaults that SQLAlchemy defers until INSERT."""
        now = datetime.now(timezone.utc)
        for attr in ("created_at", "updated_at"):
            if hasattr(obj, attr) and getattr(obj, attr) is None:
                setattr(obj, attr, now)
        # Apply Python-column defaults that SQLAlchemy only sets during INSERT
        if hasattr(obj, "is_active") and getattr(obj, "is_active") is None:
            setattr(obj, "is_active", True)

    async def delete(self, obj):
        self.deleted.append(obj)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


# ---------------------------------------------------------------------------
# Fixture: mock Redis
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_redis():
    """AsyncMock Redis client with sensible defaults for all operations."""
    redis = AsyncMock()
    redis.sismember = AsyncMock(return_value=False)
    redis.hgetall = AsyncMock(return_value={})
    redis.hget = AsyncMock(return_value=None)
    redis.get = AsyncMock(return_value=None)
    redis.hset = AsyncMock(return_value=True)
    redis.expire = AsyncMock(return_value=True)
    redis.incr = AsyncMock(return_value=1)
    redis.sadd = AsyncMock(return_value=1)
    redis.srem = AsyncMock(return_value=1)
    redis.ping = AsyncMock(return_value=True)
    redis.aclose = AsyncMock()

    pipe = MagicMock()
    pipe.incr = MagicMock(return_value=pipe)
    pipe.expire = MagicMock(return_value=pipe)
    pipe.execute = AsyncMock(return_value=[1, True, 1, True])
    redis.pipeline = MagicMock(return_value=pipe)

    return redis


# ---------------------------------------------------------------------------
# Fixture: mock DB session
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_db():
    """Fresh MockSession instance for each test."""
    return MockSession()


# ---------------------------------------------------------------------------
# User helpers
# ---------------------------------------------------------------------------

def _make_user(role: str = "merchant", merchant_id: str = "test-merchant"):
    """Return a SimpleNamespace that Pydantic can validate via from_attributes=True."""
    return types.SimpleNamespace(
        id=uuid.uuid4(),
        email=f"{role}@example.com",
        hashed_password="hashed",
        role=role,
        merchant_id=merchant_id,
        is_active=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def merchant_user():
    return _make_user("merchant", "test-merchant")


@pytest.fixture
def admin_user():
    return _make_user("admin", "admin-merchant")


# ---------------------------------------------------------------------------
# Transaction fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_tx():
    """A fully valid TransactionCreate payload."""
    return TransactionCreate(
        external_transaction_id="ext-txn-001",
        amount=Decimal("250.00"),
        currency="USD",
        card_last4="1234",
        card_bin="411111",
        cardholder_name="Jane Doe",
        merchant_category_code="5411",
        merchant_name="Corner Store",
        ip_address="203.0.113.5",
        device_fingerprint="fp-abc-123",
        country_code="US",
        city="New York",
        latitude=40.7128,
        longitude=-74.0060,
    )


# ---------------------------------------------------------------------------
# Canned layer results
# ---------------------------------------------------------------------------

@pytest.fixture
def rule_pass():
    return RuleResult(result="PASS", reasons=[])


@pytest.fixture
def rule_flag():
    return RuleResult(result="FLAG", reasons=["AMOUNT_EXCEEDS_SOFT_LIMIT"])


@pytest.fixture
def rule_block():
    return RuleResult(result="BLOCK", reasons=["BLACKLISTED_CARD"])


@pytest.fixture
def behavioral_low():
    return BehavioralResult(behavioral_score=0.10, anomalies=[])


@pytest.fixture
def behavioral_mid():
    return BehavioralResult(behavioral_score=0.35, anomalies=["NEW_DEVICE"])


@pytest.fixture
def behavioral_high():
    return BehavioralResult(behavioral_score=0.70, anomalies=["AMOUNT_SPIKE", "NEW_COUNTRY"])


@pytest.fixture
def ai_low():
    return AIResult(risk_score=15, risk_level="LOW", explanation="Low risk.", recommended_action="APPROVE")


@pytest.fixture
def ai_medium():
    return AIResult(risk_score=45, risk_level="MEDIUM", explanation="Medium risk.", recommended_action="FLAG")


@pytest.fixture
def ai_high():
    return AIResult(risk_score=65, risk_level="HIGH", explanation="High risk.", recommended_action="REVIEW")


@pytest.fixture
def ai_critical():
    return AIResult(risk_score=90, risk_level="CRITICAL", explanation="Critical risk.", recommended_action="BLOCK")
