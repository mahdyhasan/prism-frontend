"""Content decay detector — wraps the existing chat-agent scan.

Looks for pages that had meaningful traffic in the first half of a window and
lost >=20% in the second half. Classifies decay type (ranking loss, CTR loss,
demand loss, GA4-only).

Returns one finding-shape dict ready for the Insight pipeline, or None if no
pages are decaying.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from prism.ai.tools.cross_source_tools import content_decay_scan
from prism.ai.tools.schemas import ContentDecayInput
from prism.core.logging import logger

_TOP_N = 5
_LOOKBACK_DAYS = 28


def _severity(top: list[dict]) -> str:
    """Worst single page's session drop drives severity."""
    if not top:
        return "low"
    worst_pct = min(p["session_delta_pct"] for p in top)  # most negative
    if worst_pct <= -60:
        return "critical"
    if worst_pct <= -40:
        return "high"
    if worst_pct <= -25:
        return "medium"
    return "low"


async def detect_content_decay(
    db: AsyncSession,
    property_id: int,
    lookback_days: int = _LOOKBACK_DAYS,
) -> dict[str, Any] | None:
    inp = ContentDecayInput(
        property_id=property_id,
        lookback_days=lookback_days,
        min_sessions_threshold=10,
    )
    raw = await content_decay_scan(inp, db)
    pages = raw.get("decaying_pages", []) or []
    if not pages:
        logger.info("No decaying pages found", property_id=property_id)
        return None

    top = pages[:_TOP_N]
    return {
        "kind": "decay",
        "severity": _severity(top),
        "period_start": date.today() - timedelta(days=lookback_days - 1),
        "period_end": date.today(),
        "top_findings": top,
        "total_count": len(pages),
        "context": {"lookback_days": lookback_days},
        # Stable identity = sorted set of decaying page URLs in the top N.
        # Two scan runs on different days that surface the same five pages
        # are "the same finding" and won't generate a duplicate Insight.
        "content_identity": sorted(p["page"] for p in top),
    }
