"""Core Web Vitals agent tools.

These tools let the chat agent answer CWV questions by querying stored audit
rows (CWVPageAudit, CWVOriginAudit).  They never call the PSI/CrUX APIs
directly — ingestion is handled by the nightly Celery tasks.

Available tools:
  get_page_cwv           — latest CWV audit for a specific URL
  get_origin_cwv         — origin-level CrUX field data
  scan_cwv_problem_pages — pages with poor/needs-improvement CWV + high traffic
  cwv_mobile_desktop_compare — mobile vs desktop divergence for top pages
  cwv_trend              — CWV trend for a URL over recent audits
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from prism.db.models.cwv import CWVPageAudit, CWVOriginAudit


# ── Schemas ───────────────────────────────────────────────────────────────────

class GetPageCWVInput(BaseModel):
    property_id: int
    url: str = Field(..., description="Normalized page path or full URL")
    strategy: Literal["mobile", "desktop"] = "mobile"


class GetOriginCWVInput(BaseModel):
    property_id: int
    strategy: Literal["mobile", "desktop", "all_traffic"] = "mobile"


class ScanCWVProblemsInput(BaseModel):
    property_id: int
    strategy: Literal["mobile", "desktop"] = "mobile"
    status_filter: list[str] = Field(
        default=["poor", "needs_improvement"],
        description="CWV statuses to include: poor, needs_improvement, good",
    )
    limit: int = Field(20, ge=1, le=100)


class CWVMobileDesktopInput(BaseModel):
    property_id: int
    limit: int = Field(20, ge=1, le=50)


class CWVTrendInput(BaseModel):
    property_id: int
    url: str
    strategy: Literal["mobile", "desktop"] = "mobile"
    days: int = Field(30, ge=7, le=90)


# ── Tool functions ─────────────────────────────────────────────────────────────

async def get_page_cwv(inp: GetPageCWVInput, db: AsyncSession) -> dict[str, Any]:
    """Return the most recent CWV audit for a specific page + strategy."""
    # Try exact match first, then LIKE
    result = await db.execute(
        select(CWVPageAudit)
        .where(
            CWVPageAudit.property_id == inp.property_id,
            CWVPageAudit.url_normalized.like(f"%{inp.url.rstrip('/')}%"),
            CWVPageAudit.strategy == inp.strategy,
        )
        .order_by(CWVPageAudit.audited_at.desc())
        .limit(1)
    )
    row = result.scalar_one_or_none()
    if row is None:
        return {
            "found": False,
            "url": inp.url,
            "strategy": inp.strategy,
            "message": "No CWV audit found for this page. A nightly audit runs at 03:00 UTC.",
        }

    return {
        "found": True,
        "url": row.url_normalized,
        "strategy": row.strategy,
        "audited_at": row.audited_at.isoformat(),
        "cwv_status": row.cwv_status,
        "lcp_ms": row.lcp_ms,
        "inp_ms": row.inp_ms,
        "cls": row.cls,
        "fcp_ms": row.fcp_ms,
        "ttfb_ms": row.ttfb_ms,
        "lighthouse_performance_score": row.lighthouse_performance_score,
        "opportunities": row.opportunities or [],
        "diagnostics": row.diagnostics or [],
    }


async def get_origin_cwv(inp: GetOriginCWVInput, db: AsyncSession) -> dict[str, Any]:
    """Return the most recent origin-level CrUX field data."""
    result = await db.execute(
        select(CWVOriginAudit)
        .where(
            CWVOriginAudit.property_id == inp.property_id,
            CWVOriginAudit.strategy == inp.strategy,
        )
        .order_by(CWVOriginAudit.audited_at.desc())
        .limit(1)
    )
    row = result.scalar_one_or_none()
    if row is None:
        return {
            "found": False,
            "strategy": inp.strategy,
            "message": "No origin CrUX data found. Data is pulled nightly from the Chrome UX Report API.",
        }

    return {
        "found": True,
        "origin": row.origin,
        "strategy": row.strategy,
        "audited_at": row.audited_at.isoformat(),
        "cwv_status": row.cwv_status,
        "lcp_p75_ms": row.lcp_ms,
        "inp_p75_ms": row.inp_ms,
        "cls_p75": row.cls,
        "fcp_p75_ms": row.fcp_ms,
        "ttfb_p75_ms": row.ttfb_ms,
        "field_data_available": row.field_data_available,
    }


async def scan_cwv_problem_pages(inp: ScanCWVProblemsInput, db: AsyncSession) -> dict[str, Any]:
    """Find pages with poor/needs-improvement CWV from the latest audit batch.

    Returns pages sorted by LCP descending (worst first) so the agent can
    prioritize fixes by severity.
    """
    # Get the most recent audit date for this property+strategy
    latest_result = await db.execute(
        select(func.max(CWVPageAudit.audited_at))
        .where(
            CWVPageAudit.property_id == inp.property_id,
            CWVPageAudit.strategy == inp.strategy,
        )
    )
    latest_date = latest_result.scalar_one_or_none()
    if latest_date is None:
        return {
            "found": False,
            "strategy": inp.strategy,
            "message": "No CWV audits found. A nightly audit runs at 03:00 UTC.",
        }

    # Cutoff: rows from the last audit day
    cutoff = latest_date - timedelta(hours=24)

    stmt = (
        select(CWVPageAudit)
        .where(
            CWVPageAudit.property_id == inp.property_id,
            CWVPageAudit.strategy == inp.strategy,
            CWVPageAudit.audited_at >= cutoff,
            CWVPageAudit.cwv_status.in_(inp.status_filter),
        )
        .order_by(CWVPageAudit.lcp_ms.desc().nullslast())
        .limit(inp.limit)
    )
    result = await db.execute(stmt)
    rows = result.scalars().all()

    pages = [
        {
            "url": r.url_normalized,
            "cwv_status": r.cwv_status,
            "lcp_ms": r.lcp_ms,
            "inp_ms": r.inp_ms,
            "cls": r.cls,
            "lighthouse_performance_score": r.lighthouse_performance_score,
            "audited_at": r.audited_at.isoformat(),
        }
        for r in rows
    ]

    return {
        "found": True,
        "strategy": inp.strategy,
        "latest_audit_date": latest_date.isoformat(),
        "total_problem_pages": len(pages),
        "pages": pages,
        "status_filter": inp.status_filter,
    }


async def cwv_mobile_desktop_compare(
    inp: CWVMobileDesktopInput, db: AsyncSession
) -> dict[str, Any]:
    """Compare mobile vs desktop CWV for pages audited in the last 7 days.

    Surfaces pages where mobile is significantly worse than desktop — useful
    for identifying mobile-specific performance issues.
    """
    cutoff = date.today() - timedelta(days=7)

    # Fetch mobile rows
    mob_result = await db.execute(
        select(CWVPageAudit)
        .where(
            CWVPageAudit.property_id == inp.property_id,
            CWVPageAudit.strategy == "mobile",
            CWVPageAudit.audited_at >= cutoff,
        )
        .order_by(CWVPageAudit.url_normalized, CWVPageAudit.audited_at.desc())
    )
    mob_rows = mob_result.scalars().all()

    # Fetch desktop rows
    desk_result = await db.execute(
        select(CWVPageAudit)
        .where(
            CWVPageAudit.property_id == inp.property_id,
            CWVPageAudit.strategy == "desktop",
            CWVPageAudit.audited_at >= cutoff,
        )
        .order_by(CWVPageAudit.url_normalized, CWVPageAudit.audited_at.desc())
    )
    desk_rows = desk_result.scalars().all()

    mob_map: dict[str, CWVPageAudit] = {}
    seen_mob: set[str] = set()
    for r in mob_rows:
        if r.url_normalized not in seen_mob:
            mob_map[r.url_normalized] = r
            seen_mob.add(r.url_normalized)

    desk_map: dict[str, CWVPageAudit] = {}
    seen_desk: set[str] = set()
    for r in desk_rows:
        if r.url_normalized not in seen_desk:
            desk_map[r.url_normalized] = r
            seen_desk.add(r.url_normalized)

    comparisons = []
    for url, mob in mob_map.items():
        desk = desk_map.get(url)
        if desk is None:
            continue
        lcp_diff = None
        if mob.lcp_ms is not None and desk.lcp_ms is not None and desk.lcp_ms > 0:
            lcp_diff = round((mob.lcp_ms - desk.lcp_ms) / desk.lcp_ms * 100, 1)
        comparisons.append({
            "url": url,
            "mobile_status": mob.cwv_status,
            "desktop_status": desk.cwv_status,
            "mobile_lcp_ms": mob.lcp_ms,
            "desktop_lcp_ms": desk.lcp_ms,
            "lcp_mobile_overhead_pct": lcp_diff,
            "mobile_cls": mob.cls,
            "desktop_cls": desk.cls,
            "mobile_score": mob.lighthouse_performance_score,
            "desktop_score": desk.lighthouse_performance_score,
        })

    # Sort by LCP overhead descending (mobile worst vs desktop)
    comparisons.sort(
        key=lambda r: r["lcp_mobile_overhead_pct"] or 0,
        reverse=True,
    )

    return {
        "found": bool(comparisons),
        "pages_compared": len(comparisons),
        "pages": comparisons[: inp.limit],
        "note": "lcp_mobile_overhead_pct > 0 means mobile is slower than desktop",
    }


async def cwv_trend(inp: CWVTrendInput, db: AsyncSession) -> dict[str, Any]:
    """Return CWV audit history for a specific URL + strategy.

    Useful for showing whether a page's performance improved or regressed
    after a deployment.
    """
    cutoff = date.today() - timedelta(days=inp.days)
    result = await db.execute(
        select(CWVPageAudit)
        .where(
            CWVPageAudit.property_id == inp.property_id,
            CWVPageAudit.url_normalized.like(f"%{inp.url.rstrip('/')}%"),
            CWVPageAudit.strategy == inp.strategy,
            CWVPageAudit.audited_at >= cutoff,
        )
        .order_by(CWVPageAudit.audited_at.asc())
    )
    rows = result.scalars().all()

    if not rows:
        return {
            "found": False,
            "url": inp.url,
            "strategy": inp.strategy,
            "message": f"No audit history in the last {inp.days} days.",
        }

    history = [
        {
            "audited_at": r.audited_at.isoformat(),
            "cwv_status": r.cwv_status,
            "lcp_ms": r.lcp_ms,
            "inp_ms": r.inp_ms,
            "cls": r.cls,
            "lighthouse_performance_score": r.lighthouse_performance_score,
        }
        for r in rows
    ]

    return {
        "found": True,
        "url": rows[0].url_normalized,
        "strategy": inp.strategy,
        "audit_count": len(history),
        "history": history,
    }
