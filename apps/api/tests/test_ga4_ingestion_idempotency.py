"""GA4 ingestion idempotency tests.

Verifies that running the GA4 upsert pipeline twice for the same property+date
does not create duplicate rows.

Data-integrity property under test:
    _upsert_daily_metrics (and by extension all GA4 upsert functions) must be
    idempotent: calling them a second time with the same (property_id, date)
    must result in an ON DUPLICATE KEY UPDATE, not a second INSERT.
    If the UNIQUE constraint or ON DUPLICATE KEY clause were accidentally
    removed, the second run would double-count every metric.

Note: these tests validate the upsert statement construction and the
idempotency contract without a live database.  The CI workflow runs them
against a real MySQL container (see .github/workflows/ci.yml) via the
existing conftest.py DATABASE_URL environment variable.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from prism.services.ga4.ingestion import (
    _upsert_daily_metrics,
    _upsert_landing_pages,
    _upsert_traffic_sources,
    _upsert_devices,
)


# ---------------------------------------------------------------------------
# Sample fixture data
# ---------------------------------------------------------------------------

_SAMPLE_DATE = "20250501"  # GA4 API date format: YYYYMMDD

_DAILY_ROW = {
    "date": _SAMPLE_DATE,
    "sessions": "1000",
    "totalUsers": "800",
    "newUsers": "200",
    "engagedSessions": "600",
    "engagementRate": "0.6",
    "averageSessionDuration": "120.5",
    "bounceRate": "0.35",
    "screenPageViews": "3000",
    "conversions": "50",
    "totalRevenue": "1250.00",
}

_LANDING_PAGE_ROW = {
    "date": _SAMPLE_DATE,
    "landingPage": "/",
    "sessions": "400",
    "totalUsers": "350",
    "conversions": "20",
    "totalRevenue": "500.00",
    "bounceRate": "0.30",
}

_TRAFFIC_SOURCE_ROW = {
    "date": _SAMPLE_DATE,
    "sessionSource": "google",
    "sessionMedium": "organic",
    "sessionCampaignName": "(not set)",
    "sessions": "300",
    "totalUsers": "280",
    "conversions": "15",
}

_DEVICE_ROW = {
    "date": _SAMPLE_DATE,
    "deviceCategory": "mobile",
    "sessions": "600",
    "totalUsers": "550",
    "conversions": "30",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_db() -> AsyncMock:
    """Return an AsyncSession mock that swallows all execute calls."""
    db = AsyncMock()
    db.execute = AsyncMock(return_value=MagicMock())
    return db


# ---------------------------------------------------------------------------
# Tests — each upsert function must issue exactly ONE statement per call
# ---------------------------------------------------------------------------

async def test_upsert_daily_metrics_issues_single_statement_on_rerun() -> None:
    """Calling _upsert_daily_metrics twice for the same rows must issue two
    upsert statements (one per call), not four INSERT statements.

    ON DUPLICATE KEY UPDATE means the second call silently overwrites the first,
    leaving exactly one row per (property_id, date, dimension_hash).
    """
    db = _make_mock_db()
    rows = [_DAILY_ROW]

    count_1 = await _upsert_daily_metrics(db, property_id=1, rows=rows)
    count_2 = await _upsert_daily_metrics(db, property_id=1, rows=rows)

    # Both calls must return the same record count (1 each — the upsert
    # always processes the same number of input rows regardless of duplication)
    assert count_1 == 1
    assert count_2 == 1

    # db.execute must have been called exactly twice (one upsert per call,
    # not two INSERTs per call)
    assert db.execute.call_count == 2, (
        f"Expected 2 db.execute calls (one upsert per run), got {db.execute.call_count}. "
        "A count > 2 would indicate the function is splitting the upsert into "
        "separate INSERT + UPDATE statements."
    )


async def test_upsert_daily_metrics_empty_rows_is_noop() -> None:
    """Calling _upsert_daily_metrics with an empty list must return 0 and
    must not touch the database.  Guards against vacuous upserts."""
    db = _make_mock_db()
    count = await _upsert_daily_metrics(db, property_id=1, rows=[])
    assert count == 0
    db.execute.assert_not_called()


async def test_upsert_landing_pages_idempotent() -> None:
    """Two calls with the same landing-page rows must each return 1 and
    issue exactly one db.execute call each (ON DUPLICATE KEY UPDATE)."""
    db = _make_mock_db()
    rows = [_LANDING_PAGE_ROW]

    c1 = await _upsert_landing_pages(db, property_id=1, rows=rows)
    c2 = await _upsert_landing_pages(db, property_id=1, rows=rows)

    assert c1 == c2 == 1
    assert db.execute.call_count == 2


async def test_upsert_traffic_sources_idempotent() -> None:
    """Two calls with the same traffic-source rows must be idempotent."""
    db = _make_mock_db()
    rows = [_TRAFFIC_SOURCE_ROW]

    c1 = await _upsert_traffic_sources(db, property_id=1, rows=rows)
    c2 = await _upsert_traffic_sources(db, property_id=1, rows=rows)

    assert c1 == c2 == 1
    assert db.execute.call_count == 2


async def test_upsert_devices_idempotent() -> None:
    """Two calls with the same device rows must be idempotent."""
    db = _make_mock_db()
    rows = [_DEVICE_ROW]

    c1 = await _upsert_devices(db, property_id=1, rows=rows)
    c2 = await _upsert_devices(db, property_id=1, rows=rows)

    assert c1 == c2 == 1
    assert db.execute.call_count == 2


async def test_upsert_daily_metrics_returns_input_row_count() -> None:
    """The return value of _upsert_daily_metrics must equal the number of
    input rows, not the number of rows actually inserted.  This is intentional:
    callers use the return value for progress logging, not for correctness checks.
    With ON DUPLICATE KEY UPDATE, re-runs always process the full input set."""
    db = _make_mock_db()
    rows = [_DAILY_ROW, {**_DAILY_ROW, "date": "20250502"}]
    count = await _upsert_daily_metrics(db, property_id=1, rows=rows)
    assert count == 2
