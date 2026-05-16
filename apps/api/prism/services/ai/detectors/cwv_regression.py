"""CWV Regression detector.

Detects pages where Core Web Vitals got significantly worse between the
prior audit window and the current one.

Logic:
  - "Current" = most recent audit within the last 7 days
  - "Prior" = most recent audit from 7-30 days ago
  - Regression = LCP increased by >= 500ms OR cwv_status downgraded
    (good→needs_improvement or needs_improvement→poor)

Bundle kind: "cwv_regression"
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from prism.core.logging import logger
from prism.db.models.cwv import CWVPageAudit

_STRATEGY = "mobile"
_LCP_REGRESSION_MS = 500      # LCP increase threshold for a regression flag
_STATUS_ORDER = {"good": 0, "needs_improvement": 1, "poor": 2, "insufficient_data": -1}


async def detect(
    db: AsyncSession,
    property_id: int,
    ref_date: date | None = None,
) -> dict[str, Any] | None:
    """Return a CWV regression finding bundle or None."""
    if ref_date is None:
        ref_date = date.today()

    current_cutoff = ref_date - timedelta(days=7)
    prior_cutoff = ref_date - timedelta(days=30)

    # Fetch current audits (last 7 days)
    cur_result = await db.execute(
        select(CWVPageAudit)
        .where(
            CWVPageAudit.property_id == property_id,
            CWVPageAudit.strategy == _STRATEGY,
            CWVPageAudit.audited_at >= current_cutoff,
        )
        .order_by(CWVPageAudit.url_normalized, CWVPageAudit.audited_at.desc())
    )
    cur_rows = cur_result.scalars().all()

    # Keep only the most recent audit per URL
    cur_map: dict[str, CWVPageAudit] = {}
    seen: set[str] = set()
    for r in cur_rows:
        if r.url_normalized not in seen:
            cur_map[r.url_normalized] = r
            seen.add(r.url_normalized)

    if not cur_map:
        logger.debug("CWV regression: no recent audits", property_id=property_id)
        return None

    # Fetch prior audits (7-30 days ago)
    prior_result = await db.execute(
        select(CWVPageAudit)
        .where(
            CWVPageAudit.property_id == property_id,
            CWVPageAudit.strategy == _STRATEGY,
            CWVPageAudit.audited_at >= prior_cutoff,
            CWVPageAudit.audited_at < current_cutoff,
            CWVPageAudit.url_normalized.in_(list(cur_map.keys())),
        )
        .order_by(CWVPageAudit.url_normalized, CWVPageAudit.audited_at.desc())
    )
    prior_rows = prior_result.scalars().all()

    prior_map: dict[str, CWVPageAudit] = {}
    seen_prior: set[str] = set()
    for r in prior_rows:
        if r.url_normalized not in seen_prior:
            prior_map[r.url_normalized] = r
            seen_prior.add(r.url_normalized)

    if not prior_map:
        return None

    findings: list[dict[str, Any]] = []
    for url, cur in cur_map.items():
        prior = prior_map.get(url)
        if prior is None:
            continue

        lcp_delta = None
        lcp_regression = False
        if cur.lcp_ms is not None and prior.lcp_ms is not None:
            lcp_delta = cur.lcp_ms - prior.lcp_ms
            lcp_regression = lcp_delta >= _LCP_REGRESSION_MS

        status_regression = False
        cur_order = _STATUS_ORDER.get(cur.cwv_status or "", -1)
        prior_order = _STATUS_ORDER.get(prior.cwv_status or "", -1)
        if cur_order > 0 and prior_order >= 0 and cur_order > prior_order:
            status_regression = True

        if not lcp_regression and not status_regression:
            continue

        score_delta = None
        if cur.lighthouse_performance_score is not None and prior.lighthouse_performance_score is not None:
            score_delta = round(cur.lighthouse_performance_score - prior.lighthouse_performance_score, 1)

        findings.append({
            "url": url,
            "current_cwv_status": cur.cwv_status,
            "prior_cwv_status": prior.cwv_status,
            "current_lcp_ms": cur.lcp_ms,
            "prior_lcp_ms": prior.lcp_ms,
            "lcp_delta_ms": lcp_delta,
            "current_score": cur.lighthouse_performance_score,
            "prior_score": prior.lighthouse_performance_score,
            "score_delta": score_delta,
            "lcp_regression": lcp_regression,
            "status_regression": status_regression,
            "audited_at": cur.audited_at.isoformat(),
        })

    if not findings:
        return None

    # Sort by LCP delta descending
    findings.sort(key=lambda r: r["lcp_delta_ms"] or 0, reverse=True)
    top = findings[:5]

    severe = [f for f in findings if f["current_cwv_status"] == "poor"]
    severity = "high" if len(severe) >= 2 else "medium" if len(severe) >= 1 else "low"

    return {
        "kind": "cwv_regression",
        "top_findings": top,
        "total_count": len(findings),
        "severity": severity,
        "content_identity": sorted(f["url"] for f in top),
        "period_start": prior_cutoff,
        "period_end": ref_date,
        "context": {"strategy": _STRATEGY},
    }
