"""CWV Mobile vs Desktop divergence detector.

Identifies pages where mobile CWV is significantly worse than desktop.
This surfaces mobile-specific issues that affect the majority of users
and can damage Google mobile-first rankings.

Triggers when:
  - Mobile LCP >= Desktop LCP + 2000ms  (mobile is 2s+ slower)
  - OR mobile status is "poor" while desktop is "good" or "needs_improvement"

Bundle kind: "cwv_mobile_desktop"
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from prism.core.logging import logger
from prism.db.models.cwv import CWVPageAudit

_LOOKBACK_DAYS = 7
_LCP_GAP_MS = 2000   # mobile must be this much worse than desktop to flag
_STATUS_ORDER = {"good": 0, "needs_improvement": 1, "poor": 2, "insufficient_data": -1}


async def detect(
    db: AsyncSession,
    property_id: int,
    ref_date: date | None = None,
) -> dict[str, Any] | None:
    """Return a mobile/desktop divergence bundle or None."""
    if ref_date is None:
        ref_date = date.today()

    cutoff = ref_date - timedelta(days=_LOOKBACK_DAYS)

    # Fetch recent audits for both strategies
    result = await db.execute(
        select(CWVPageAudit)
        .where(
            CWVPageAudit.property_id == property_id,
            CWVPageAudit.audited_at >= cutoff,
            CWVPageAudit.strategy.in_(["mobile", "desktop"]),
        )
        .order_by(CWVPageAudit.url_normalized, CWVPageAudit.audited_at.desc())
    )
    rows = result.scalars().all()

    # Build per-URL, per-strategy latest audit maps
    mob_map: dict[str, CWVPageAudit] = {}
    desk_map: dict[str, CWVPageAudit] = {}
    seen_mob: set[str] = set()
    seen_desk: set[str] = set()

    for r in rows:
        if r.strategy == "mobile" and r.url_normalized not in seen_mob:
            mob_map[r.url_normalized] = r
            seen_mob.add(r.url_normalized)
        elif r.strategy == "desktop" and r.url_normalized not in seen_desk:
            desk_map[r.url_normalized] = r
            seen_desk.add(r.url_normalized)

    if not mob_map or not desk_map:
        logger.debug("CWV mobile/desktop: insufficient data", property_id=property_id)
        return None

    findings: list[dict[str, Any]] = []
    for url, mob in mob_map.items():
        desk = desk_map.get(url)
        if desk is None:
            continue

        lcp_gap = None
        lcp_flag = False
        if mob.lcp_ms is not None and desk.lcp_ms is not None:
            lcp_gap = mob.lcp_ms - desk.lcp_ms
            lcp_flag = lcp_gap >= _LCP_GAP_MS

        mob_order = _STATUS_ORDER.get(mob.cwv_status or "", -1)
        desk_order = _STATUS_ORDER.get(desk.cwv_status or "", -1)
        status_flag = mob_order > 0 and desk_order >= 0 and mob_order > desk_order + 1

        if not lcp_flag and not status_flag:
            continue

        score_gap = None
        if mob.lighthouse_performance_score is not None and desk.lighthouse_performance_score is not None:
            score_gap = round(desk.lighthouse_performance_score - mob.lighthouse_performance_score, 1)

        findings.append({
            "url": url,
            "mobile_cwv_status": mob.cwv_status,
            "desktop_cwv_status": desk.cwv_status,
            "mobile_lcp_ms": mob.lcp_ms,
            "desktop_lcp_ms": desk.lcp_ms,
            "lcp_gap_ms": lcp_gap,
            "mobile_score": mob.lighthouse_performance_score,
            "desktop_score": desk.lighthouse_performance_score,
            "score_gap": score_gap,
            "mobile_cls": mob.cls,
            "desktop_cls": desk.cls,
        })

    if not findings:
        return None

    findings.sort(key=lambda r: r["lcp_gap_ms"] or 0, reverse=True)
    top = findings[:5]

    severity = (
        "high" if len(findings) >= 5
        else "medium" if len(findings) >= 2
        else "low"
    )

    return {
        "kind": "cwv_mobile_desktop",
        "top_findings": top,
        "total_count": len(findings),
        "severity": severity,
        "content_identity": sorted(f["url"] for f in top),
        "period_start": cutoff,
        "period_end": ref_date,
        "context": {"lcp_gap_threshold_ms": _LCP_GAP_MS},
    }
