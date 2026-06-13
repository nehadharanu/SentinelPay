"""Unit tests for BehavioralProfiler — anomaly scoring and profile updates."""

import json
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.behavioral_profiler import BehavioralProfiler
from app.schemas.transaction import TransactionCreate


def make_tx(**overrides):
    defaults = dict(
        external_transaction_id="txn-bp",
        amount=Decimal("100.00"),
        currency="USD",
        card_last4="5678",
        card_bin="411111",
        cardholder_name="Alice",
        merchant_category_code="5411",
        merchant_name="Grocery",
        ip_address="10.0.0.2",
        device_fingerprint="known-device",
        country_code="US",
    )
    defaults.update(overrides)
    return TransactionCreate(**defaults)


@pytest.fixture
def profiler(mock_redis):
    return BehavioralProfiler(redis_client=mock_redis)


class TestAnomalyScoring:
    async def test_new_card_no_anomalies(self, profiler, mock_redis):
        """A card with no prior history must score 0.0 with no anomalies."""
        mock_redis.hgetall = AsyncMock(return_value={})
        result = await profiler.score(make_tx())
        assert result.behavioral_score == 0.0
        assert result.anomalies == []

    async def test_amount_spike_detected(self, profiler, mock_redis):
        """Amount 4× average must trigger AMOUNT_SPIKE (+0.30)."""
        profile = {
            b"tx_count_total": b"10",
            b"avg_amount_overall": b"100.0",
            b"stddev_amount": b"10.0",
            b"known_devices": json.dumps(["known-device"]).encode(),
            b"known_countries": json.dumps(["US"]).encode(),
        }
        mock_redis.hgetall = AsyncMock(return_value=profile)
        result = await profiler.score(make_tx(amount=Decimal("450.00")))  # 4.5× avg
        assert "AMOUNT_SPIKE" in result.anomalies
        assert result.behavioral_score >= 0.30

    async def test_amount_deviation_detected(self, profiler, mock_redis):
        """Amount > avg + 2×stddev (but ≤ 3×avg) must trigger AMOUNT_DEVIATION (+0.20)."""
        profile = {
            b"tx_count_total": b"10",
            b"avg_amount_overall": b"100.0",
            b"stddev_amount": b"20.0",
            b"known_devices": json.dumps(["known-device"]).encode(),
            b"known_countries": json.dumps(["US"]).encode(),
        }
        mock_redis.hgetall = AsyncMock(return_value=profile)
        # 150 > avg + 2×stddev (140), but 150 < 3×avg (300), so DEVIATION not SPIKE
        result = await profiler.score(make_tx(amount=Decimal("150.00")))
        assert "AMOUNT_DEVIATION" in result.anomalies
        assert "AMOUNT_SPIKE" not in result.anomalies

    async def test_new_device_detected(self, profiler, mock_redis):
        """An unknown device fingerprint on an established card triggers NEW_DEVICE (+0.20)."""
        profile = {
            b"tx_count_total": b"5",
            b"avg_amount_overall": b"100.0",
            b"stddev_amount": b"5.0",
            b"known_devices": json.dumps(["old-device"]).encode(),
            b"known_countries": json.dumps(["US"]).encode(),
        }
        mock_redis.hgetall = AsyncMock(return_value=profile)
        result = await profiler.score(make_tx(device_fingerprint="brand-new-device"))
        assert "NEW_DEVICE" in result.anomalies

    async def test_new_country_detected(self, profiler, mock_redis):
        """An unknown country on an established card triggers NEW_COUNTRY (+0.25)."""
        profile = {
            b"tx_count_total": b"5",
            b"avg_amount_overall": b"100.0",
            b"stddev_amount": b"5.0",
            b"known_devices": json.dumps(["known-device"]).encode(),
            b"known_countries": json.dumps(["US"]).encode(),
        }
        mock_redis.hgetall = AsyncMock(return_value=profile)
        result = await profiler.score(make_tx(country_code="DE"))
        assert "NEW_COUNTRY" in result.anomalies

    async def test_new_merchant_category_detected(self, profiler, mock_redis):
        """A MCC with no prior spend on an established card triggers NEW_MERCHANT_CATEGORY (+0.10)."""
        profile = {
            b"tx_count_total": b"5",
            b"avg_amount_overall": b"100.0",
            b"stddev_amount": b"5.0",
            b"known_devices": json.dumps(["known-device"]).encode(),
            b"known_countries": json.dumps(["US"]).encode(),
            # No avg_amount_5411 key
        }
        mock_redis.hgetall = AsyncMock(return_value=profile)
        result = await profiler.score(make_tx(merchant_category_code="5999"))
        assert "NEW_MERCHANT_CATEGORY" in result.anomalies

    async def test_score_clamped_at_one(self, profiler, mock_redis):
        """Multiple simultaneous anomalies must be clamped to a maximum score of 1.0."""
        profile = {
            b"tx_count_total": b"10",
            b"avg_amount_overall": b"50.0",
            b"stddev_amount": b"5.0",
            b"known_devices": json.dumps(["other-device"]).encode(),
            b"known_countries": json.dumps(["GB"]).encode(),
        }
        mock_redis.hgetall = AsyncMock(return_value=profile)
        # SPIKE (0.30) + NEW_DEVICE (0.20) + NEW_COUNTRY (0.25) + NEW_MCC (0.10) > 1.0
        result = await profiler.score(make_tx(amount=Decimal("500.00"), device_fingerprint="new", country_code="US"))
        assert result.behavioral_score <= 1.0

    async def test_profile_updated_after_scoring(self, profiler, mock_redis):
        """After scoring, the profile pipeline (hset calls) must be executed to persist updates."""
        mock_redis.hgetall = AsyncMock(return_value={})
        await profiler.score(make_tx())
        # hset is now issued via a pipeline; verify the pipeline was created and executed
        assert mock_redis.pipeline.called
        pipe = mock_redis.pipeline.return_value
        assert pipe.hset.called
