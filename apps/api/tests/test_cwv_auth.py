"""Cross-property CWV authorization tests.

These tests verify that a user who does not own a property cannot access its
CWV data.  They are designed to *fail* until the ownership guard is added to
the CWV routes — running them on the current codebase will expose BLOCKER-1:
the CWV endpoints trust the JWT user but do not check PropertyMember membership.

Security property under test:
    GET /properties/{id}/cwv/origin and GET /properties/{id}/cwv/settings
    must return 403 when the authenticated user is not a member of property {id}.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from prism.main import app
from prism.db.models.user import User
from prism.db.models.tenant import Tenant
from prism.db.models.property import Property, PropertyMember
from prism.db.session import get_db_session
from prism.services.auth import create_access_token


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_route_mock_db() -> AsyncMock:
    """Return an AsyncMock session suitable for the CWV route handlers.

    The route handlers call ``db.execute(...)`` and read
    ``scalar_one_or_none()`` on the result.  Returning ``None`` from
    ``scalar_one_or_none`` makes the routes return their "no data" default
    responses (200 with empty/default payload), which is fine for auth tests
    that only assert on the status code.
    """
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_result.scalars.return_value.all.return_value = []
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    return mock_session


@pytest.fixture
async def client() -> AsyncClient:
    # Override the route-level get_db_session so the CWV handlers never hit
    # the real database.  The middleware's get_db_session is patched separately
    # (per-test via _mock_db_returning_user) to resolve the JWT user.
    route_db = _make_route_mock_db()
    app.dependency_overrides[get_db_session] = lambda: route_db
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            yield ac
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def tenant_1() -> Tenant:
    t = Tenant(name="acme", slug="acme", plan="free")
    t.id = 101
    return t


@pytest.fixture
def tenant_2() -> Tenant:
    t = Tenant(name="other", slug="other", plan="free")
    t.id = 102
    return t


@pytest.fixture
def user_1(tenant_1: Tenant) -> User:
    """Owner of property_a."""
    u = User(tenant_id=tenant_1.id, email="alice@acme.com", name="Alice", role="owner")
    u.id = 201
    return u


@pytest.fixture
def user_2(tenant_2: Tenant) -> User:
    """Owner of property_b — a completely different account."""
    u = User(tenant_id=tenant_2.id, email="bob@other.com", name="Bob", role="owner")
    u.id = 202
    return u


@pytest.fixture
def property_a(tenant_1: Tenant) -> Property:
    p = Property(
        tenant_id=tenant_1.id,
        display_name="Acme Site",
        ga4_property_id="properties/111",
        status="active",
    )
    p.id = 301
    return p


@pytest.fixture
def property_b(tenant_2: Tenant) -> Property:
    p = Property(
        tenant_id=tenant_2.id,
        display_name="Other Site",
        ga4_property_id="properties/222",
        status="active",
    )
    p.id = 302
    return p


@pytest.fixture
def token_user_1(user_1: User) -> str:
    return create_access_token(user_1)


@pytest.fixture
def token_user_2(user_2: User) -> str:
    return create_access_token(user_2)


def _mock_db_returning_user(user: User):
    """Return a context-manager patch that makes get_current_user resolve to `user`."""
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = user
    mock_session.execute = AsyncMock(return_value=mock_result)
    mock_session.__aenter__ = AsyncMock(return_value=mock_session)
    mock_session.__aexit__ = AsyncMock(return_value=False)
    return patch("prism.core.middleware.get_db_session", return_value=mock_session)


# ---------------------------------------------------------------------------
# Tests — cross-property access must be rejected
# ---------------------------------------------------------------------------

async def test_cwv_origin_rejects_non_owner(
    client: AsyncClient,
    user_1: User,
    token_user_1: str,
    property_b: Property,
) -> None:
    """User 1 must not read CWV origin data for property B (owned by user 2).

    Expected: 403 Forbidden.
    Current state: likely returns 200 because there is no ownership check —
    this test is intended to fail until the guard is added (BLOCKER-1).
    """
    with _mock_db_returning_user(user_1):
        res = await client.get(
            f"/api/v1/properties/{property_b.id}/cwv/origin",
            headers={"Authorization": f"Bearer {token_user_1}"},
        )
    assert res.status_code == 403, (
        f"Expected 403, got {res.status_code}. "
        "CWV /origin is missing a PropertyMember ownership check."
    )


async def test_cwv_settings_rejects_non_owner(
    client: AsyncClient,
    user_1: User,
    token_user_1: str,
    property_b: Property,
) -> None:
    """User 1 must not read CWV settings for property B (owned by user 2).

    Expected: 403 Forbidden.
    Current state: likely returns 200 because there is no ownership check.
    """
    with _mock_db_returning_user(user_1):
        res = await client.get(
            f"/api/v1/properties/{property_b.id}/cwv/settings",
            headers={"Authorization": f"Bearer {token_user_1}"},
        )
    assert res.status_code == 403, (
        f"Expected 403, got {res.status_code}. "
        "CWV /settings is missing a PropertyMember ownership check."
    )


async def test_cwv_origin_allows_owner(
    client: AsyncClient,
    user_1: User,
    token_user_1: str,
    property_a: Property,
) -> None:
    """User 1 must be able to read CWV origin data for their own property A.

    Expected: not 403 (typically 200 with empty data in a test DB).
    """
    with _mock_db_returning_user(user_1):
        res = await client.get(
            f"/api/v1/properties/{property_a.id}/cwv/origin",
            headers={"Authorization": f"Bearer {token_user_1}"},
        )
    assert res.status_code != 403, (
        "Ownership check incorrectly rejected the property owner."
    )


async def test_cwv_origin_rejects_unauthenticated(
    client: AsyncClient,
    property_a: Property,
) -> None:
    """Requests without a JWT must return 401, not 403 or 200."""
    res = await client.get(f"/api/v1/properties/{property_a.id}/cwv/origin")
    assert res.status_code == 401
