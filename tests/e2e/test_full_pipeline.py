"""End-to-end test: submit transaction → receive fraud decision.

All external I/O (DB, Redis, Anthropic) is mocked; the complete 3-layer
pipeline runs with realistic data to verify the wiring between layers.
"""

import json
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.dependencies import get_current_user, get_fraud_engine
from app.main import app
from app.models.transaction import Transaction
from app.models.fraud_decision import FraudDecision
from app.services.ai_scorer import AIResult, AIScorer
from app.services.behavioral_profiler import BehavioralProfiler, BehavioralResult
from app.services.fraud_engine import FraudEngine, FraudDecisionResult
from app.services.rule_engine import RuleEngine, RuleResult
from tests.integration.conftest import _auth_headers, _make_db_user


def _tx_payload(ext_id=None, amount="200.00"):
    return {
        "external_transaction_id": ext_id or f"e2e-{uuid.uuid4()}",
        "amount": amount,
        "currency": "USD",
        "card_last4": "9999",
        "card_bin": "411111",
        "cardholder_name": "Eve Test",
        "merchant_category_code": "5411",
        "merchant_name": "E2E Mart",
        "ip_address": "203.0.113.99",
        "device_fingerprint": "fp-e2e",
        "country_code": "US",
        "city": "Portland",
        "latitude": 45.52,
        "longitude": -122.68,
    }


class TestFullPipelineApproved:
    async def test_normal_transaction_approved(self, client, mock_db, mock_redis):
        """A normal, low-risk transaction flows through all 3 layers and returns APPROVE."""
        merchant = _make_db_user(role="merchant", merchant_id="e2e-merchant")
        mock_db.push(scalar=None)  # duplicate-check

        # Redis: no blacklist hits, no velocity issues, empty profile
        mock_redis.sismember = AsyncMock(return_value=False)
        mock_redis.get = AsyncMock(return_value=b"0")
        mock_redis.hgetall = AsyncMock(return_value={})
        mock_redis.hget = AsyncMock(return_value=None)

        # Build a real FraudEngine wired with mocked rules (empty cache)
        rule_engine = RuleEngine(redis_client=mock_redis, db_session_factory=MagicMock())
        rule_engine._rules_cache = []
        rule_engine._cache_loaded_at = float("inf")

        behavioral = BehavioralProfiler(redis_client=mock_redis)

        ai_response_json = json.dumps({
            "risk_score": 12,
            "risk_level": "LOW",
            "explanation": "Normal transaction with no red flags.",
            "recommended_action": "APPROVE",
        })
        mock_msg = MagicMock()
        mock_msg.content = [MagicMock(text=ai_response_json)]

        ai_scorer = AIScorer()
        with patch.object(ai_scorer._client.messages, "create", new=AsyncMock(return_value=mock_msg)):
            engine = FraudEngine(rule_engine, behavioral, ai_scorer)

            app.dependency_overrides[get_current_user] = lambda: merchant
            app.dependency_overrides[get_fraud_engine] = lambda: engine
            try:
                resp = await client.post(
                    "/api/v1/transactions/analyze",
                    json=_tx_payload(),
                    headers=_auth_headers(merchant),
                )
            finally:
                app.dependency_overrides.pop(get_current_user, None)
                app.dependency_overrides.pop(get_fraud_engine, None)

        assert resp.status_code == 200
        body = resp.json()
        assert body["final_decision"] == "APPROVE"
        assert body["layers"]["rule_engine"]["result"] == "PASS"
        assert body["layers"]["ai_scorer"]["risk_level"] == "LOW"


class TestFullPipelineBlocked:
    async def test_blacklisted_card_blocked_immediately(self, client, mock_db, mock_redis):
        """A transaction on a blacklisted card is blocked in Layer 1; AI is not called."""
        merchant = _make_db_user(role="merchant", merchant_id="e2e-merchant-2")
        mock_db.push(scalar=None)  # duplicate-check

        # Card is blacklisted
        async def _sismember(key, val):
            return "cards" in key
        mock_redis.sismember = _sismember

        rule_engine = RuleEngine(redis_client=mock_redis, db_session_factory=MagicMock())
        rule_engine._rules_cache = []
        rule_engine._cache_loaded_at = float("inf")

        behavioral = BehavioralProfiler(redis_client=mock_redis)
        ai_scorer = AIScorer()

        ai_called = []

        async def _ai_should_not_be_called(*args, **kwargs):
            ai_called.append(True)
            return MagicMock()

        with patch.object(ai_scorer._client.messages, "create", new=_ai_should_not_be_called):
            engine = FraudEngine(rule_engine, behavioral, ai_scorer)

            app.dependency_overrides[get_current_user] = lambda: merchant
            app.dependency_overrides[get_fraud_engine] = lambda: engine
            try:
                resp = await client.post(
                    "/api/v1/transactions/analyze",
                    json=_tx_payload(),
                    headers=_auth_headers(merchant),
                )
            finally:
                app.dependency_overrides.pop(get_current_user, None)
                app.dependency_overrides.pop(get_fraud_engine, None)

        assert resp.status_code == 200
        body = resp.json()
        assert body["final_decision"] == "BLOCK"
        assert body["layers"]["rule_engine"]["result"] == "BLOCK"
        assert body["layers"]["ai_scorer"]["skipped"] is True
        assert ai_called == [], "AI scorer must not be called when Layer 1 blocks"


class TestFullPipelineHighRisk:
    async def test_high_behavioral_score_reviewed(self, client, mock_db, mock_redis):
        """A transaction with high behavioral anomaly score is escalated to REVIEW."""
        merchant = _make_db_user(role="merchant", merchant_id="e2e-merchant-3")
        mock_db.push(scalar=None)  # duplicate-check

        mock_redis.sismember = AsyncMock(return_value=False)
        mock_redis.get = AsyncMock(return_value=b"0")
        mock_redis.hget = AsyncMock(return_value=None)

        # Profile with known history → several anomalies will fire
        profile = {
            b"tx_count_total": b"20",
            b"avg_amount_overall": b"50.0",
            b"stddev_amount": b"10.0",
            b"known_devices": json.dumps(["other-device"]).encode(),
            b"known_countries": json.dumps(["GB"]).encode(),
        }
        mock_redis.hgetall = AsyncMock(return_value=profile)

        rule_engine = RuleEngine(redis_client=mock_redis, db_session_factory=MagicMock())
        rule_engine._rules_cache = []
        rule_engine._cache_loaded_at = float("inf")

        behavioral = BehavioralProfiler(redis_client=mock_redis)

        # AI returns HIGH risk
        ai_response_json = json.dumps({
            "risk_score": 70,
            "risk_level": "HIGH",
            "explanation": "Multiple anomalies detected.",
            "recommended_action": "REVIEW",
        })
        mock_msg = MagicMock()
        mock_msg.content = [MagicMock(text=ai_response_json)]

        ai_scorer = AIScorer()
        with patch.object(ai_scorer._client.messages, "create", new=AsyncMock(return_value=mock_msg)):
            engine = FraudEngine(rule_engine, behavioral, ai_scorer)

            app.dependency_overrides[get_current_user] = lambda: merchant
            app.dependency_overrides[get_fraud_engine] = lambda: engine
            try:
                resp = await client.post(
                    "/api/v1/transactions/analyze",
                    # $300 is 6× the $50 average → AMOUNT_SPIKE; new device + new country too
                    json=_tx_payload(amount="300.00"),
                    headers=_auth_headers(merchant),
                )
            finally:
                app.dependency_overrides.pop(get_current_user, None)
                app.dependency_overrides.pop(get_fraud_engine, None)

        assert resp.status_code == 200
        body = resp.json()
        # behavioral_score > 0.55 (spike + new_device + new_country) → REVIEW
        assert body["final_decision"] in ("REVIEW", "BLOCK")
