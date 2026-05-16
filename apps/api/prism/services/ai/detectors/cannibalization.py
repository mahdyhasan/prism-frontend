"""SEO cannibalization detector — wraps the existing chat-agent scan.

Finds queries where multiple pages on the same site are competing
(both ranking with non-trivial impressions). Recommends the page with the
highest conversion rate as canonical.

Returns one finding-shape dict ready for the Insight pipeline, or None.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from prism.ai.tools.cross_source_tools import cannibalization_scan
from prism.ai.tools.schemas import CannibalizationInput, DateRangeInput
from prism.core.logging import logger

_TOP_N = 5
_LOOKBACK_DAYS = 28


def _severity(queries: list[dict]) -> str:
    """Severity rises with how many queries are affected."""
    n = len(queries)
    if n >= 20:
        return "high"
    if n >= 10:
        return "medium"
    return "low"


async def detect_cannibalization(
    db: AsyncSession,
    property_id: int,
    lookback_days: int = _LOOKBACK_DAYS,
) -> dict[str, Any] | None:
    end = date.today()
    start = end - timedelta(days=lookback_days - 1)

    inp = CannibalizationInput(
        property_id=property_id,
        date_range=DateRangeInput(start=start.isoformat(), end=end.isoformat()),
        impression_threshold=50,
    )
    raw = await cannibalization_scan(inp, db)
    queries = raw.get("cannibalized_queries", []) or []
    if not queries:
        logger.info("No cannibalization found", property_id=property_id)
        return None

    top = queries[:_TOP_N]
    return {
        "kind": "cannibalization",
        "severity": _severity(queries),
        "period_start": start,
        "period_end": end,
        "top_findings": top,
        "total_count": len(queries),
        "context": {"lookback_days": lookback_days, "impression_threshold": 50},
        # Stable identity = sorted set of competing queries in the top N.
        "content_identity": sorted(q["query"] for q in top),
    }
