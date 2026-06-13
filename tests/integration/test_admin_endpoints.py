"""Integration tests for /api/v1/admin/* endpoints."""

import types
import uuid
from datetime import datetime, timezone

import pytest

from app.dependencies import get_current_user
from app.main import app
from tests.conftest import _make_user
from tests.integration.conftest import _auth_headers, _make_db_user


def _make_decision(**kwargs):
    return types.SimpleNamespace(
        id=uuid.uuid4(),
        transaction_id=uuid.uuid4(),
        layer1_result=kwargs.get("layer1_result", "PASS"),
        layer2_behavioral_score=kwargs.get("layer2_behavioral_score", 0.1),
        layer3_risk_score=kwargs.get("layer3_risk_score", 20),
        final_decision=kwargs.get("final_decision", "APPROVE"),
        processing_ms=kwargs.get("processing_ms", 50),
        created_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def admin():
    return _make_db_user(role="admin", merchant_id="admin-mid")


@pytest.fixture
def merchant():
    return _make_db_user(role="merchant", merchant_id="merch-mid")


class TestMetrics:
    async def test_admin_gets_metrics(self, client, mock_db, admin):
        """Admin can GET /admin/metrics and receives an aggregated stats dict."""
        decisions = [
            _make_decision(final_decision="APPROVE", processing_ms=30),
            _make_decision(final_decision="BLOCK", processing_ms=10, layer1_result="BLOCK"),
        ]
        mock_db.push(scalar=None, scalars_list=decisions)

        app.dependency_overrides[get_current_user] = lambda: admin
        try:
            resp = await client.get("/api/v1/admin/metrics", headers=_auth_headers(admin))
        finally:
            app.dependency_overrides.pop(get_current_user, None)

        assert resp.status_code == 200
        body = resp.json()
        assert "totals" in body
        assert body["totals"]["transactions_analyzed"] == 2
        assert body["totals"]["blocked"] == 1

    async def test_merchant_cannot_access_metrics(self, client, merchant):
        """A merchant calling /admin/metrics gets 403 FORBIDDEN."""
        app.dependency_overrides[get_current_user] = lambda: merchant
        try:
            resp = await client.get("/api/v1/admin/metrics", headers=_auth_headers(merchant))
        finally:
            app.dependency_overrides.pop(get_current_user, None)

        assert resp.status_code == 403


class TestListUsers:
    async def test_admin_lists_all_users(self, client, mock_db, admin):
        """Admin can GET /admin/users and receives a paginated user list."""
        users = [_make_user("merchant", "m1"), _make_user("admin", "m2")]
        mock_db.push(scalar=2)                         # count query
        mock_db.push(scalar=None, scalars_list=users)  # rows query

        app.dependency_overrides[get_current_user] = lambda: admin
        try:
            resp = await client.get("/api/v1/admin/users", headers=_auth_headers(admin))
        finally:
            app.dependency_overrides.pop(get_current_user, None)

        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 2
        assert len(body["items"]) == 2


class TestUpdateUserRole:
    async def test_admin_can_update_user_role(self, client, mock_db, admin):
        """Admin can change another user's role."""
        target = _make_db_user(role="merchant", merchant_id="target-mid")
        mock_db.push(scalar=target)

        app.dependency_overrides[get_current_user] = lambda: admin
        try:
            resp = await client.put(
                f"/api/v1/admin/users/{target.id}/role",
                json={"role": "admin"},
                headers=_auth_headers(admin),
            )
        finally:
            app.dependency_overrides.pop(get_current_user, None)

        assert resp.status_code == 200

    async def test_admin_cannot_demote_self(self, client, mock_db, admin):
        """An admin cannot downgrade their own role; returns 400 CANNOT_DEMOTE_SELF."""
        mock_db.push(scalar=admin)

        app.dependency_overrides[get_current_user] = lambda: admin
        try:
            resp = await client.put(
                f"/api/v1/admin/users/{admin.id}/role",
                json={"role": "merchant"},
                headers=_auth_headers(admin),
            )
        finally:
            app.dependency_overrides.pop(get_current_user, None)

        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "CANNOT_DEMOTE_SELF"

    async def test_update_nonexistent_user_returns_404(self, client, mock_db, admin):
        """Updating a user UUID that does not exist returns 404."""
        mock_db.push(scalar=None)

        app.dependency_overrides[get_current_user] = lambda: admin
        try:
            resp = await client.put(
                f"/api/v1/admin/users/{uuid.uuid4()}/role",
                json={"role": "merchant"},
                headers=_auth_headers(admin),
            )
        finally:
            app.dependency_overrides.pop(get_current_user, None)

        assert resp.status_code == 404
