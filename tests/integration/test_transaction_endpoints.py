"""Integration tests for /api/v1/transactions/* endpoints."""

import types
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.core.security import create_access_token
from app.dependencies import get_current_user, get_fraud_engine
from app.main import app
from app.services.ai_scorer import AIResult
from app.services.behavioral_profiler import BehavioralResult
from app.services.fraud_engine import FraudDecisionResult
from app.services.rule_engine import RuleResult
from tests.conftest import MockSession, _make_user
from tests.integration.conftest import _auth_headers, _make_db_user


def _make_tx_body(**overrides):
    base = {
        "external_transaction_id": f"ext-{uuid.uuid4()}",
        "amount": "150.00",
        "currency": "USD",
        "card_last4": "4242",
        "card_bin": "424242",
        "cardholder_name": "Bob Smith",
        "merchant_category_code": "5411",
        "merchant_name": "Fast Shop",
        "ip_address": "198.51.100.7",
        "device_fingerprint": "fp-bob-001",
        "country_code": "US",
        "city": "Austin",
        "latitude": 30.27,
        "longitude": -97.74,
    }
    base.update(overrides)
    return base


def _canned_fraud_result(decision="APPROVE") -> FraudDecisionResult:
    return FraudDecisionResult(
        final_decision=decision,
        recommended_action=decision,
        processing_ms=42,
        rule_result=RuleResult(result="PASS", reasons=[]),
        behavioral_result=BehavioralResult(behavioral_score=0.05, anomalies=[]),
        ai_result=AIResult(
            risk_score=10,
            risk_level="LOW",
            explanation="Looks fine.",
            recommended_action=decision,
        ),
    )


def _canned_transaction(merchant_id="test-merchant"):
    return types.SimpleNamespace(
        id=uuid.uuid4(),
        merchant_id=merchant_id,
        external_transaction_id=f"ext-{uuid.uuid4()}",
        amount=Decimal("150.00"),
        currency="USD",
        card_last4="4242",
        card_bin="424242",
        cardholder_name="Bob Smith",
        merchant_category_code="5411",
        merchant_name="Fast Shop",
        ip_address="198.51.100.7",
        device_fingerprint="fp-bob-001",
        country_code="US",
        city="Austin",
        latitude=30.27,
        longitude=-97.74,
        created_at=datetime.now(timezone.utc),
    )


def _canned_decision(tx):
    return types.SimpleNamespace(
        id=uuid.uuid4(),
        transaction_id=tx.id,
        layer1_result="PASS",
        layer1_reasons=[],
        layer2_behavioral_score=0.05,
        layer2_anomalies=[],
        layer3_risk_score=10,
        layer3_risk_level="LOW",
        layer3_explanation="Looks fine.",
        final_decision="APPROVE",
        recommended_action="APPROVE",
        processing_ms=42,
        created_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def merchant():
    return _make_db_user(role="merchant", merchant_id="test-merchant")


@pytest.fixture
def admin():
    return _make_db_user(role="admin", merchant_id="admin-mid")


class TestAnalyzeTransaction:
    async def test_analyze_success_returns_fraud_decision(self, client, mock_db, merchant):
        """A valid transaction submitted by an authenticated merchant returns a fraud decision."""
        mock_engine = AsyncMock()
        mock_engine.analyze = AsyncMock(return_value=_canned_fraud_result("APPROVE"))

        mock_db.push(scalar=None)       # duplicate-check → no existing tx

        app.dependency_overrides[get_current_user] = lambda: merchant
        app.dependency_overrides[get_fraud_engine] = lambda: mock_engine

        try:
            resp = await client.post(
                "/api/v1/transactions/analyze",
                json=_make_tx_body(),
                headers=_auth_headers(merchant),
            )
        finally:
            app.dependency_overrides.pop(get_current_user, None)
            app.dependency_overrides.pop(get_fraud_engine, None)

        assert resp.status_code == 200
        body = resp.json()
        assert body["final_decision"] == "APPROVE"
        assert "layers" in body

    async def test_analyze_duplicate_transaction_returns_409(self, client, mock_db, merchant):
        """Submitting the same external_transaction_id twice returns 409."""
        existing_tx = _canned_transaction()
        mock_db.push(scalar=merchant)   # get_current_user
        mock_db.push(scalar=existing_tx)  # duplicate-check finds existing

        app.dependency_overrides[get_current_user] = lambda: merchant

        try:
            resp = await client.post(
                "/api/v1/transactions/analyze",
                json=_make_tx_body(external_transaction_id=existing_tx.external_transaction_id),
                headers=_auth_headers(merchant),
            )
        finally:
            app.dependency_overrides.pop(get_current_user, None)

        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "DUPLICATE_TRANSACTION"

    async def test_analyze_unauthenticated_returns_4xx(self, client):
        """Calling /analyze without a Bearer token returns 401 or 403."""
        resp = await client.post("/api/v1/transactions/analyze", json=_make_tx_body())
        assert resp.status_code in (401, 403)


class TestGetTransaction:
    async def test_get_own_transaction_returns_200(self, client, mock_db, merchant):
        """A merchant can retrieve their own transaction by UUID."""
        tx = _canned_transaction(merchant_id=merchant.merchant_id)
        mock_db.push(scalar=tx)

        app.dependency_overrides[get_current_user] = lambda: merchant
        try:
            resp = await client.get(
                f"/api/v1/transactions/{tx.id}",
                headers=_auth_headers(merchant),
            )
        finally:
            app.dependency_overrides.pop(get_current_user, None)

        assert resp.status_code == 200

    async def test_merchant_cannot_get_other_merchant_transaction(self, client, mock_db, merchant):
        """A merchant requesting another merchant's transaction gets 403."""
        tx = _canned_transaction(merchant_id="other-merchant")
        mock_db.push(scalar=tx)

        app.dependency_overrides[get_current_user] = lambda: merchant
        try:
            resp = await client.get(
                f"/api/v1/transactions/{tx.id}",
                headers=_auth_headers(merchant),
            )
        finally:
            app.dependency_overrides.pop(get_current_user, None)

        assert resp.status_code == 403

    async def test_get_nonexistent_transaction_returns_404(self, client, mock_db, merchant):
        """Requesting a transaction UUID that does not exist returns 404."""
        mock_db.push(scalar=None)  # get_by_id returns None → TransactionNotFound

        app.dependency_overrides[get_current_user] = lambda: merchant
        try:
            resp = await client.get(
                f"/api/v1/transactions/{uuid.uuid4()}",
                headers=_auth_headers(merchant),
            )
        finally:
            app.dependency_overrides.pop(get_current_user, None)

        assert resp.status_code == 404


class TestGetDecision:
    async def test_get_decision_returns_fraud_detail(self, client, mock_db, merchant):
        """A merchant can fetch the fraud decision for their own transaction."""
        tx = _canned_transaction(merchant_id=merchant.merchant_id)
        decision = _canned_decision(tx)
        mock_db.push(scalar=tx)        # get_by_id
        mock_db.push(scalar=decision)  # get_decision_by_transaction_id

        app.dependency_overrides[get_current_user] = lambda: merchant
        try:
            resp = await client.get(
                f"/api/v1/transactions/{tx.id}/decision",
                headers=_auth_headers(merchant),
            )
        finally:
            app.dependency_overrides.pop(get_current_user, None)

        assert resp.status_code == 200
        body = resp.json()
        assert body["final_decision"] == "APPROVE"
