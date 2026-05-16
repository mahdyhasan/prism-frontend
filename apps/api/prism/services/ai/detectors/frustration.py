"""Frustration insight detector — surfaces pages with abnormally high
Clarity frustration scores.

Two conditions trigger an Insight:
1. **Spike**: frustration_score jumped by >= 50% vs the prior 14-day window.
2. **Top decile**: frustration_score is among the highest 20% of all pages AND
   the page has at least 50 sessions in the window.

Returns one bundle dict (same shape as the other cross-source detectors) or
None when there is no Clarity data or no findings above the threshold.

Bundle shape (matches _persist_finding_bundle expectations):
    {
        "kind": "frustration",
        "top_findings": [...],   # up to 5 entries
        "total_count": N,        # total pages analyzed
        "severity": "high|medium|low",
        "content_identity": [...],   # sorted list of top page_urls (for dedupe)
        "period_start": date,
        "period_end": date,
    }
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from prism.core.logging import logger
from prism.db.models.clarity import ClarityPageDaily

_MIN_SESSIONS = 50
_LOOKBACK = 14      # days in each window
_FRUSTRATION_CAP = 3.0  # normalisation cap for (dead + 2*rage + quick) / sessions


def _frust(dead: int, rage: int, quick: int, sessions: int) -> float | None:
    if not sessions:
        return None
    raw = (dead + 2 * rage + quick) / float(sessions)
    return round(min(raw / _FRUSTRATION_CAP, 1.0), 4)


async def detect(
    db: AsyncSession,
    property_id: int,
    ref_date: date | None = None,
) -> dict[str, Any] | None:
    """Return a frustration finding bundle or None."""
    if ref_date is None:
        ref_date = date.today()

    current_end = ref_date - timedelta(days=1)
    current_start = current_end - timedelta(days=_LOOKBACK - 1)
    prior_end = current_start - timedelta(days=1)
    prior_start = prior_end - timedelta(days=_LOOKBACK - 1)

    # ── Aggregate current window ──────────────────────────────────────────────
    current_result = await db.execute(
        select(
            ClarityPageDaily.page_url,
            func.sum(ClarityPageDaily.dead_clicks).label("dead"),
            func.sum(ClarityPageDaily.rage_clicks).label("rage"),
            func.sum(ClarityPageDaily.quick_backs).label("quick"),
            func.sum(ClarityPageDaily.session_count).label("sessions"),
            func.avg(ClarityPageDaily.scroll_depth_avg).label("scroll"),
        )
        .where(
            ClarityPageDaily.property_id == property_id,
            ClarityPageDaily.date >= current_start,
            ClarityPageDaily.date <= current_end,
        )
        .group_by(ClarityPageDaily.page_url)
        .having(func.sum(ClarityPageDaily.session_count) >= _MIN_SESSIONS)
    )
    current_rows = current_result.mappings().all()

    if not current_rows:
        logger.debug("Frustration detector: no Clarity data", property_id=property_id)
        return None

    # ── Aggregate prior window (for spike detection) ──────────────────────────
    prior_result = await db.execute(
        select(
            ClarityPageDaily.page_url,
            func.sum(ClarityPageDaily.dead_clicks).label("dead"),
            func.sum(ClarityPageDaily.rage_clicks).label("rage"),
            func.sum(ClarityPageDaily.quick_backs).label("quick"),
            func.sum(ClarityPageDaily.session_count).label("sessions"),
        )
        .where(
            ClarityPageDaily.property_id == property_id,
            ClarityPageDaily.date >= prior_start,
            ClarityPageDaily.date <= prior_end,
        )
        .group_by(ClarityPageDaily.page_url)
    )
    prior_map: dict[str, float] = {}
    for row in prior_result.mappings().all():
        fs = _frust(int(row["dead"] or 0), int(row["rage"] or 0),
                    int(row["quick"] or 0), int(row["sessions"] or 0))
        if fs is not None:
            prior_map[row["page_url"]] = fs

    # ── Build per-page entries ────────────────────────────────────────────────
    entries: list[dict[str, Any]] = []
    for row in current_rows:
        dead = int(row["dead"] or 0)
        rage = int(row["rage"] or 0)
        quick = int(row["quick"] or 0)
        sessions = int(row["sessions"] or 0)
        scroll = round(float(row["scroll"] or 0), 3)
        fs = _frust(dead, rage, quick, sessions)
        if fs is None:
            continue
        prior_fs = prior_map.get(row["page_url"])
        spike = (
            prior_fs is not None
            and prior_fs > 0
            and (fs - prior_fs) / prior_fs >= 0.50
        )
        entries.append({
            "page_url": row["page_url"],
            "frustration_score": fs,
            "prior_frustration_score": prior_fs,
            "sessions": sessions,
            "dead_clicks": dead,
            "rage_clicks": rage,
            "quick_backs": quick,
            "scroll_depth_avg": scroll,
            "is_spike": spike,
        })

    if not entries:
        return None

    # ── Select findings: spikes + top-decile high-frustration pages ───────────
    sorted_by_fs = sorted(entries, key=lambda r: r["frustration_score"], reverse=True)
    top_cutoff = sorted_by_fs[0]["frustration_score"] * 0.80
    findings = [
        e for e in sorted_by_fs
        if e["is_spike"] or e["frustration_score"] >= top_cutoff
    ][:5]

    if not findings:
        return None

    top = findings[0]
    severity = (
        "high" if top["frustration_score"] >= 0.6
        else "medium" if top["frustration_score"] >= 0.3
        else "low"
    )

    return {
        "kind": "frustration",
        "top_findings": findings,
        "total_count": len(entries),
        "severity": severity,
        "content_identity": sorted(f["page_url"] for f in findings),
        "period_start": current_start,
        "period_end": current_end,
    }
