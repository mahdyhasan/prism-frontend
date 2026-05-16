"""CWV Traffic-Impact detector.

Finds pages that have both:
  - A poor or needs-improvement Core Web Vitals status
  - Significant organic traffic (sessions >= threshold)

These are the highest-ROI pages for performance improvement: fixing them would
benefit the most users and could improve Google rankings.

Bundle shape (matches _persist_finding_bundle):
    {
        "kind": "cwv_traffic_impact",
        "top_findings": [...],
        "total_count": N,
        "severity": "high|medium|low",
        "content_identity": [sorted list of url_normalized for dedupe],
        "period_start": date,
        "period_end": date,
        "context": {"strategy": "mobile"},
    }
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from prism.core.logging import logger
from prism.db.models.cwv import CWVPageAudit
from prism.db.models.cross_source import XSPageDaily

_MIN_SESSIONS = 500   # pages with this many sessions are "significant traffic"
_LOOKBACK_DAYS = 28   # sessions window
_STRATEGY = "mobile"  # mobile-first; most impactful for rankings


async def detect(
    db: AsyncSession,
    property_id: int,
    ref_date: date | None = None,
) -> dict[str, Any] | None:
    """Return a CWV traffic-impact finding bundle or None."""
    if ref_date is None:
        ref_date = date.today()

    traffic_start = ref_date - timedelta(days=_LOOKBACK_DAYS)

    # Get the most recent audit date for this property
    latest_result = await db.execute(
        select(func.max(CWVPageAudit.audited_at))
        .where(
            CWVPageAudit.property_id == property_id,
            CWVPageAudit.strategy == _STRATEGY,
        )
    )
    latest_audit = latest_result.scalar_one_or_none()
    if latest_audit is None:
        logger.debug("CWV traffic-impact: no audits found", property_id=property_id)
        return None

    audit_cutoff = latest_audit - timedelta(hours=24)

    # Fetch problematic pages from recent audit
    audit_result = await db.execute(
        select(CWVPageAudit)
        .where(
            CWVPageAudit.property_id == property_id,
            CWVPageAudit.strategy == _STRATEGY,
            CWVPageAudit.audited_at >= audit_cutoff,
            CWVPageAudit.cwv_status.in_(["poor", "needs_improvement"]),
        )
    )
    audit_rows = {r.url_normalized: r for r in audit_result.scalars().all()}
    if not audit_rows:
        return None

    # Fetch traffic for those pages
    traffic_result = await db.execute(
        select(
            XSPageDaily.page_url_normalized,
            func.sum(XSPageDaily.sessions).label("sessions"),
            func.sum(XSPageDaily.conversions).label("conversions"),
        )
        .where(
            XSPageDaily.property_id == property_id,
            XSPageDaily.date >= traffic_start,
            XSPageDaily.date <= ref_date,
            XSPageDaily.page_url_normalized.in_(list(audit_rows.keys())),
        )
        .group_by(XSPageDaily.page_url_normalized)
        .having(func.sum(XSPageDaily.sessions) >= _MIN_SESSIONS)
    )
    traffic_map: dict[str, dict] = {
        r["page_url_normalized"]: {
            "sessions": int(r["sessions"] or 0),
            "conversions": int(r["conversions"] or 0),
        }
        for r in traffic_result.mappings().all()
    }

    if not traffic_map:
        return None

    # Build findings: pages with poor CWV AND high traffic
    findings: list[dict[str, Any]] = []
    for url, traffic in traffic_map.items():
        audit = audit_rows.get(url)
        if audit is None:
            continue
        findings.append({
            "url": url,
            "cwv_status": audit.cwv_status,
            "lcp_ms": audit.lcp_ms,
            "inp_ms": audit.inp_ms,
            "cls": audit.cls,
            "lighthouse_performance_score": audit.lighthouse_performance_score,
            "sessions_28d": traffic["sessions"],
            "conversions_28d": traffic["conversions"],
        })

    if not findings:
        return None

    # Sort by sessions descending (highest traffic impact first)
    findings.sort(key=lambda r: r["sessions_28d"], reverse=True)
    top = findings[:5]

    # Severity: based on how many "poor" pages are in the list
    poor_count = sum(1 for f in findings if f["cwv_status"] == "poor")
    severity = "high" if poor_count >= 3 else "medium" if poor_count >= 1 else "low"

    return {
        "kind": "cwv_traffic_impact",
        "top_findings": top,
        "total_count": len(findings),
        "severity": severity,
        "content_identity": sorted(f["url"] for f in top),
        "period_start": traffic_start,
        "period_end": ref_date,
        "context": {
            "strategy": _STRATEGY,
            "min_sessions": _MIN_SESSIONS,
            "audit_date": latest_audit.isoformat() if latest_audit else None,
        },
    }
