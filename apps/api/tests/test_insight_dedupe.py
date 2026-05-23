"""Insight pipeline idempotency tests.

Verifies that running the nightly insight pipeline twice for the same property
and the same underlying findings does not produce duplicate Insight rows.

Data-integrity property under test:
    Two consecutive runs of _persist_finding_bundle (or generate_cross_source_insights)
    with identical findings must yield exactly one Insight row in the database.
    The deduplication key is the content_hash stored in supporting_data, which
    is derived from (kind, content_identity).  This test would fail if the
    content_hash check were removed, silently flooding the insights table.
"""
from __future__ import annotations

from datetime import date
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from prism.services.ai.insights import _compute_content_hash, _persist_finding_bundle


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_bundle(kind: str = "decay", identity: list[str] | None = None) -> dict[str, Any]:
    """Build a minimal detector bundle that _persist_finding_bundle accepts."""
    return {
        "kind": kind,
        "total_count": 3,
        "severity": "medium",
        "top_findings": [
            {"page": "/blog/old-post", "sessions": 10},
            {"page": "/blog/older-post", "sessions": 5},
        ],
        "content_identity": identity or ["/blog/old-post", "/blog/older-post"],
        "context": {},
        "period_start": date(2025, 5, 1),
        "period_end": date(2025, 5, 7),
    }


def _make_existing_insight_row(content_hash: str) -> MagicMock:
    """Return a row mock that looks like an Insight with the given content_hash."""
    row = MagicMock()
    row.supporting_data = {"content_hash": content_hash}
    return row


# ---------------------------------------------------------------------------
# Unit test: _compute_content_hash is deterministic
# ---------------------------------------------------------------------------

def test_content_hash_is_stable_across_calls() -> None:
    """The same (kind, identity) must always produce the same 16-char hex hash.

    If this were non-deterministic the dedupe check would never fire.
    """
    h1 = _compute_content_hash("decay", ["/blog/old-post", "/blog/older-post"])
    h2 = _compute_content_hash("decay", ["/blog/old-post", "/blog/older-post"])
    assert h1 == h2
    assert len(h1) == 16


def test_content_hash_is_order_independent() -> None:
    """Identity list is sorted before hashing so insertion order does not matter."""
    h1 = _compute_content_hash("decay", ["b", "a"])
    h2 = _compute_content_hash("decay", ["a", "b"])
    assert h1 == h2


def test_content_hash_differs_for_different_findings() -> None:
    """Different findings produce different hashes — no false-positive deduplication."""
    h1 = _compute_content_hash("decay", ["/page-a"])
    h2 = _compute_content_hash("decay", ["/page-b"])
    assert h1 != h2


# ---------------------------------------------------------------------------
# Integration-style test: second run is a no-op
# ---------------------------------------------------------------------------

async def test_second_run_skips_duplicate_insight() -> None:
    """_persist_finding_bundle must return 0 (skipped) when an Insight with the
    same content_hash already exists in the database.

    This simulates two consecutive nightly pipeline runs for the same property.
    Run 1 creates the row (mocked as already committed).
    Run 2 must detect the hash match and return 0 without inserting a new row.
    """
    bundle = _make_bundle()
    content_hash = _compute_content_hash(bundle["kind"], bundle["content_identity"])

    # Simulate the DB already containing an insight with this content_hash
    existing_row = _make_existing_insight_row(content_hash)

    mock_session = AsyncMock()
    # The first execute (dup check query) returns a result with one existing row
    dup_result = MagicMock()
    dup_result.all.return_value = [existing_row]
    mock_session.execute = AsyncMock(return_value=dup_result)

    result = await _persist_finding_bundle(
        db=mock_session,
        bundle=bundle,
        tenant_id=1,
        property_id=42,
    )

    assert result == 0, (
        "_persist_finding_bundle must return 0 when a matching content_hash exists. "
        "A non-zero return means a duplicate row was (or would be) inserted."
    )
    # db.add must NOT have been called for a new row
    mock_session.add.assert_not_called()


async def test_first_run_creates_insight() -> None:
    """_persist_finding_bundle must return 1 when no matching insight exists yet.

    Confirms that the dedupe check does not over-block the first legitimate insert.
    """
    bundle = _make_bundle()

    mock_session = AsyncMock()
    # No existing rows for this property/kind
    dup_result = MagicMock()
    dup_result.all.return_value = []
    mock_session.execute = AsyncMock(return_value=dup_result)
    mock_session.commit = AsyncMock()

    # Stub out Claude narration so the test has no external dependency
    with patch(
        "prism.services.ai.insights.call_claude",
        new_callable=AsyncMock,
        return_value='{"title": "3 decaying pages detected", "summary": "Top: /blog/old-post", "severity": "medium"}',
    ):
        result = await _persist_finding_bundle(
            db=mock_session,
            bundle=bundle,
            tenant_id=1,
            property_id=42,
        )

    assert result == 1, (
        "_persist_finding_bundle must return 1 when no duplicate exists. "
        "A return of 0 would mean legitimate insights are silently dropped."
    )
    mock_session.add.assert_called_once()
