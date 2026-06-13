"""E2E conftest — re-expose the integration client fixture to the e2e package."""

from tests.integration.conftest import (  # noqa: F401
    client,
    _make_db_user,
    _token_for,
    _auth_headers,
)
