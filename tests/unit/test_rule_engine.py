"""Unit tests for RuleEngine — blacklist, amount, velocity, and geo rules."""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone, timedelta

import pytest

from app.services.rule_engine import RuleEngine
from app.schemas.transaction import TransactionCreate


def make_tx(**kwargs):
    defaults = dict(
        external_transaction_id="txn-test",
        amount=Decimal("100.00"),
        currency="USD",
        card_last4="1234",
        card_bin="411111",
        cardholder_name="Test User",
        merchant_category_code="5411",
        merchant_name="Shop",
        ip_address="10.0.0.1",
        device_fingerprint="device-fp",
        country_code="US",
    )
    defaults.update(kwargs)
    return TransactionCreate(**defaults)


@pytest.fixture
def engine(mock_redis):
    """RuleEngine with a mock Redis client and an empty DB factory."""
    db_factory = MagicMock()
    engine = RuleEngine(redis_client=mock_redis, db_session_factory=db_factory)
    # Pre-populate cache so _load_rules is never called
    engine._rules_cache = []
    engine._cache_loaded_at = float("inf")
    return engine


class TestBlacklistRules:
    async def test_card_in_blacklist_returns_block(self, engine, mock_redis):
        """A card on the blacklist must result in an immediate BLOCK."""
        mock_redis.sismember = AsyncMock(side_effect=lambda key, val: key.endswith("cards"))
        result = await engine.evaluate(make_tx())
        assert result.result == "BLOCK"
        assert "BLACKLISTED_CARD" in result.reasons

    async def test_ip_in_blacklist_returns_block(self, engine, mock_redis):
        """An IP on the blacklist must result in an immediate BLOCK."""
        async def _sismember(key, val):
            return "ips" in key
        mock_redis.sismember = _sismember
        result = await engine.evaluate(make_tx())
        assert result.result == "BLOCK"
        assert "BLACKLISTED_IP" in result.reasons

    async def test_device_in_blacklist_returns_block(self, engine, mock_redis):
        """A device fingerprint on the blacklist must result in an immediate BLOCK."""
        async def _sismember(key, val):
            return "devices" in key
        mock_redis.sismember = _sismember
        result = await engine.evaluate(make_tx())
        assert result.result == "BLOCK"
        assert "BLACKLISTED_DEVICE" in result.reasons

    async def test_clean_transaction_not_blacklisted(self, engine, mock_redis):
        """A transaction with no blacklist hits must return PASS."""
        mock_redis.sismember = AsyncMock(return_value=False)
        result = await engine.evaluate(make_tx())
        assert result.result == "PASS"


class TestAmountRules:
    def _engine_with_amount_rule(self, mock_redis, threshold, action):
        db_factory = MagicMock()
        e = RuleEngine(redis_client=mock_redis, db_session_factory=db_factory)
        e._rules_cache = [
            {"rule_type": "amount", "action": action, "condition": {"threshold": threshold}, "name": "test"}
        ]
        e._cache_loaded_at = float("inf")
        return e

    async def test_amount_exceeds_hard_limit_blocks(self, mock_redis):
        """An amount above the hard-limit threshold results in BLOCK."""
        engine = self._engine_with_amount_rule(mock_redis, 50000.0, "BLOCK")
        mock_redis.sismember = AsyncMock(return_value=False)
        result = await engine.evaluate(make_tx(amount=Decimal("60000.00")))
        assert result.result == "BLOCK"
        assert "AMOUNT_EXCEEDS_HARD_LIMIT" in result.reasons

    async def test_amount_exceeds_soft_limit_flags(self, mock_redis):
        """An amount above the soft-limit threshold results in FLAG."""
        engine = self._engine_with_amount_rule(mock_redis, 10000.0, "FLAG")
        mock_redis.sismember = AsyncMock(return_value=False)
        result = await engine.evaluate(make_tx(amount=Decimal("15000.00")))
        assert result.result == "FLAG"
        assert "AMOUNT_EXCEEDS_SOFT_LIMIT" in result.reasons

    async def test_amount_below_threshold_passes(self, mock_redis):
        """An amount below the soft limit must produce no amount reason code."""
        engine = self._engine_with_amount_rule(mock_redis, 10000.0, "FLAG")
        mock_redis.sismember = AsyncMock(return_value=False)
        result = await engine.evaluate(make_tx(amount=Decimal("50.00")))
        assert result.result == "PASS"

    async def test_fallback_soft_limit_fires_with_empty_db(self, mock_redis):
        """With no amount rules in the DB cache a $15,000 transaction triggers the settings fallback."""
        db_factory = MagicMock()
        engine = RuleEngine(redis_client=mock_redis, db_session_factory=db_factory)
        engine._rules_cache = []          # no DB rules at all
        engine._cache_loaded_at = float("inf")
        mock_redis.sismember = AsyncMock(return_value=False)
        result = await engine.evaluate(make_tx(amount=Decimal("15000.00")))
        assert result.result == "FLAG"
        assert "AMOUNT_EXCEEDS_SOFT_LIMIT" in result.reasons

    async def test_fallback_hard_limit_fires_with_empty_db(self, mock_redis):
        """With no amount rules in the DB cache a $60,000 transaction triggers the settings fallback."""
        db_factory = MagicMock()
        engine = RuleEngine(redis_client=mock_redis, db_session_factory=db_factory)
        engine._rules_cache = []
        engine._cache_loaded_at = float("inf")
        mock_redis.sismember = AsyncMock(return_value=False)
        result = await engine.evaluate(make_tx(amount=Decimal("60000.00")))
        assert result.result == "BLOCK"
        assert "AMOUNT_EXCEEDS_HARD_LIMIT" in result.reasons


class TestVelocityRules:
    def _engine_with_velocity_rule(self, mock_redis, window_seconds, threshold, action):
        db_factory = MagicMock()
        e = RuleEngine(redis_client=mock_redis, db_session_factory=db_factory)
        e._rules_cache = [
            {
                "rule_type": "velocity",
                "action": action,
                "condition": {"window_seconds": window_seconds, "threshold": threshold},
                "name": "vel",
            }
        ]
        e._cache_loaded_at = float("inf")
        return e

    async def test_velocity_1h_exceeded_flags(self, mock_redis):
        """Exceeding 1-hour velocity threshold must produce VELOCITY_1H_EXCEEDED."""
        mock_redis.sismember = AsyncMock(return_value=False)
        mock_redis.get = AsyncMock(return_value=b"6")  # count = 6 >= threshold 5
        engine = self._engine_with_velocity_rule(mock_redis, 3600, 5, "FLAG")
        result = await engine.evaluate(make_tx())
        assert result.result == "FLAG"
        assert "VELOCITY_1H_EXCEEDED" in result.reasons

    async def test_velocity_24h_exceeded_blocks(self, mock_redis):
        """Exceeding 24-hour velocity threshold with BLOCK action must produce BLOCK."""
        mock_redis.sismember = AsyncMock(return_value=False)
        mock_redis.get = AsyncMock(return_value=b"25")
        engine = self._engine_with_velocity_rule(mock_redis, 86400, 20, "BLOCK")
        result = await engine.evaluate(make_tx())
        assert result.result == "BLOCK"
        assert "VELOCITY_24H_EXCEEDED" in result.reasons

    async def test_velocity_within_threshold_passes(self, mock_redis):
        """Card count below velocity threshold must not produce a reason code."""
        mock_redis.sismember = AsyncMock(return_value=False)
        mock_redis.get = AsyncMock(return_value=b"2")
        engine = self._engine_with_velocity_rule(mock_redis, 3600, 5, "FLAG")
        result = await engine.evaluate(make_tx())
        assert result.result == "PASS"


class TestGeoRules:
    def _engine_with_geo_rule(self, mock_redis):
        db_factory = MagicMock()
        e = RuleEngine(redis_client=mock_redis, db_session_factory=db_factory)
        e._rules_cache = [
            {
                "rule_type": "geo",
                "action": "FLAG",
                "condition": {"max_distance_km": 500.0, "min_hours": 2.0},
                "name": "geo",
            }
        ]
        e._cache_loaded_at = float("inf")
        return e

    async def test_impossible_travel_flags(self, mock_redis):
        """London → New York in 1 hour must be flagged as IMPOSSIBLE_TRAVEL."""
        mock_redis.sismember = AsyncMock(return_value=False)
        # Last transaction was in London 1 hour ago
        last_ts = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        mock_redis.hget = AsyncMock(side_effect=lambda key, field: {
            "last_tx_country": b"GB",
            "last_tx_lat": b"51.51",
            "last_tx_lon": b"-0.13",
            "last_tx_timestamp": last_ts.encode(),
        }.get(field))
        engine = self._engine_with_geo_rule(mock_redis)
        # New York transaction
        tx = make_tx(country_code="US", latitude=40.71, longitude=-74.01)
        result = await engine.evaluate(tx)
        assert "IMPOSSIBLE_TRAVEL" in result.reasons

    async def test_no_previous_location_skips_geo(self, mock_redis):
        """A transaction with no previous profile must skip geo evaluation."""
        mock_redis.sismember = AsyncMock(return_value=False)
        mock_redis.hget = AsyncMock(return_value=None)
        engine = self._engine_with_geo_rule(mock_redis)
        result = await engine.evaluate(make_tx(latitude=40.71, longitude=-74.01))
        assert result.result == "PASS"
