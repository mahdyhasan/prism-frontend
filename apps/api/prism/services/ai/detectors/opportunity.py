"""SERP opportunity detector — wraps the existing chat-agent scan.

Finds queries ranking at positions 8–20 with non-trivial impressions: pages
that are *just barely* off the first page where a content tweak or backlink
push could meaningfully move clicks.

Returns one finding-shape dict ready for the Insight pipeline, or None.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from prism.ai.tools.cross_source_tools import serp_opportunity_scan
from prism.ai.tools.schemas import SerpOpportunityInput
from prism.core.logging import logger

_TOP_N = 5
_LOOKBACK_DAYS = 28


def _severity(opportunities: list[dict]) -> str:
    """Severity rises with total impressions in scope (bigger upside)."""
    total_impressions = sum(o.get("total_impressions", 0) for o in opportunities)
    if total_impressions >= 50_000:
        return "high"
    if total_impressions >= 10_000:
        return "medium"
    return "low"


async def detect_serp_opportunities(
    db: AsyncSession,
    property_id: int,
    lookback_days: int = _LOOKBACK_DAYS,
) -> dict[str, Any] | None:
    inp = SerpOpportunityInput(
        property_id=property_id,
        min_position=8.0,
        max_position=20.0,
        min_impressions=50,
    )
    raw = await serp_opportunity_scan(inp, db)
    opportunities = raw.get("opportunities", []) or []
    if not opportunities:
        logger.info("No SERP opportunities found", property_id=property_id)
        return None

    top = opportunities[:_TOP_N]
    return {
        "kind": "opportunity",
        "severity": _severity(opportunities),
        "period_start": date.today() - timedelta(days=lookback_days - 1),
        "period_end": date.today(),
        "top_findings": top,
        "total_count": len(opportunities),
        "context": {
            "lookback_days": lookback_days,
            "position_band": "8-20",
        },
        # Stable identity = sorted set of opportunity queries in the top N.
        "content_identity": sorted(o["query"] for o in top),
    }
