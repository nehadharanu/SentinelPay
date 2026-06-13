"""Integration tests for /api/v1/rules/* endpoints (admin-only)."""

import types
import uuid
from datetime import datetime, timezone

import pytest

from app.dependencies import get_current_user
from app.main import app
from tests.integration.conftest import _auth_headers, _make_db_user


def _make_rule(**overrides):
    return types.SimpleNamespace(
        id=uuid.uuid4(),
        name=overrides.get("name", "test-rule"),
        rule_type=overrides.get("rule_type", "amount"),
        condition=overrides.get("condition", {"threshold": 10000.0}),
        action=overrides.get("action", "FLAG"),
        is_active=overrides.get("is_active", True),
        created_by=uuid.uuid4(),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def admin():
    return _make_db_user(role="admin", merchant_id="admin-mid")


@pytest.fixture
def merchant():
    return _make_db_user(role="merchant", merchant_id="merch-mid")


class TestListRules:
    async def test_admin_can_list_rules(self, client, mock_db, admin):
        """Admin can GET /rules/ and receives a paginated response."""
        rule = _make_rule()
        mock_db.push(scalar=1, scalars_list=None)     # count query
        mock_db.push(scalar=None, scalars_list=[rule])  # rows query

        app.dependency_overrides[get_current_user] = lambda: admin
        try:
            resp = await client.get("/api/v1/rules/", headers=_auth_headers(admin))
        finally:
            app.dependency_overrides.pop(get_current_user, None)

        assert resp.status_code == 200
        body = resp.json()
        assert "items" in body
        assert body["total"] == 1

    async def test_merchant_cannot_list_rules(self, client, mock_db, merchant):
        """Merchant calling /rules/ receives 403 FORBIDDEN."""
        app.dependency_overrides[get_current_user] = lambda: merchant
        try:
            resp = await client.get("/api/v1/rules/", headers=_auth_headers(merchant))
        finally:
            app.dependency_overrides.pop(get_current_user, None)

        assert resp.status_code == 403


class TestCreateRule:
    async def test_admin_creates_rule_returns_201(self, client, mock_db, admin):
        """Admin can POST /rules/ to create a new rule; returns 201."""
        rule = _make_rule()
        mock_db.push(scalar=None)   # duplicate name check → no existing
        # add + commit + refresh handled by mock session

        app.dependency_overrides[get_current_user] = lambda: admin
        try:
            resp = await client.post(
                "/api/v1/rules/",
                json={
                    "name": rule.name,
                    "rule_type": "amount",
                    "condition": {"threshold": 10000.0},
                    "action": "FLAG",
                    "is_active": True,
                },
                headers=_auth_headers(admin),
            )
        finally:
            app.dependency_overrides.pop(get_current_user, None)

        assert resp.status_code == 201

    async def test_duplicate_rule_name_returns_400(self, client, mock_db, admin):
        """Creating a rule with a name that already exists returns 400."""
        existing = _make_rule()
        mock_db.push(scalar=existing)  # name-check finds existing

        app.dependency_overrides[get_current_user] = lambda: admin
        try:
            resp = await client.post(
                "/api/v1/rules/",
                json={
                    "name": existing.name,
                    "rule_type": "amount",
                    "condition": {"threshold": 5000.0},
                    "action": "FLAG",
                },
                headers=_auth_headers(admin),
            )
        finally:
            app.dependency_overrides.pop(get_current_user, None)

        assert resp.status_code == 400
        assert resp.json()["error"]["code"] == "RULE_NAME_ALREADY_EXISTS"


class TestUpdateAndDeleteRules:
    async def test_admin_updates_rule(self, client, mock_db, admin):
        """Admin can PUT /rules/{id} to update a rule."""
        rule = _make_rule()
        mock_db.push(scalar=rule)  # lookup for update

        app.dependency_overrides[get_current_user] = lambda: admin
        try:
            resp = await client.put(
                f"/api/v1/rules/{rule.id}",
                json={"action": "BLOCK"},
                headers=_auth_headers(admin),
            )
        finally:
            app.dependency_overrides.pop(get_current_user, None)

        assert resp.status_code == 200

    async def test_update_nonexistent_rule_returns_404(self, client, mock_db, admin):
        """Updating a rule UUID that does not exist returns 404."""
        mock_db.push(scalar=None)

        app.dependency_overrides[get_current_user] = lambda: admin
        try:
            resp = await client.put(
                f"/api/v1/rules/{uuid.uuid4()}",
                json={"action": "BLOCK"},
                headers=_auth_headers(admin),
            )
        finally:
            app.dependency_overrides.pop(get_current_user, None)

        assert resp.status_code == 404

    async def test_admin_deletes_rule(self, client, mock_db, admin):
        """Admin can DELETE /rules/{id}; returns 204 No Content."""
        rule = _make_rule()
        mock_db.push(scalar=rule)

        app.dependency_overrides[get_current_user] = lambda: admin
        try:
            resp = await client.delete(
                f"/api/v1/rules/{rule.id}",
                headers=_auth_headers(admin),
            )
        finally:
            app.dependency_overrides.pop(get_current_user, None)

        assert resp.status_code == 204

    async def test_admin_toggles_rule(self, client, mock_db, admin):
        """Admin can PUT /rules/{id}/toggle to enable or disable a rule."""
        rule = _make_rule(is_active=True)
        mock_db.push(scalar=rule)

        app.dependency_overrides[get_current_user] = lambda: admin
        try:
            resp = await client.put(
                f"/api/v1/rules/{rule.id}/toggle",
                json={"is_active": False},
                headers=_auth_headers(admin),
            )
        finally:
            app.dependency_overrides.pop(get_current_user, None)

        assert resp.status_code == 200
        assert resp.json()["is_active"] is False
