"""Trend detector — flags significant sustained movement in headline GA4 metrics.

Compares the last 14 days vs the prior 14 days for sessions, conversions, and
total_revenue. Flags metrics where the % change exceeds a threshold AND the
absolute traffic floor is meaningful (avoids "trend up 300% on 2 sessions/day"
noise).

Returns one finding-shape dict ready for the Insight pipeline, or None.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from prism.core.logging import logger
from prism.db.models.ga4 import GA4DailyMetrics

# Metrics we monitor and their minimum daily-baseline floor before we'd
# call a percentage change a "trend" (avoids noise from low-volume metrics).
_METRICS: tuple[tuple[str, str, float], ...] = (
    # (column_name, display_name, min_daily_baseline)
    ("sessions",      "Sessions",      50),
    ("conversions",   "Conversions",   5),
    ("total_revenue", "Revenue",       0),  # any revenue is worth narrating
)

_WINDOW_DAYS = 14
_DELTA_THRESHOLD_PCT = 20.0  # |%change| must exceed this to be a trend


async def _sum_metric(
    db: AsyncSession, property_id: int, column_name: str, start: date, end: date,
) -> float:
    col = getattr(GA4DailyMetrics, column_name)
    from sqlalchemy import func as _func
    result = await db.execute(
        select(_func.coalesce(_func.sum(col), 0))
        .where(
            GA4DailyMetrics.property_id == property_id,
            GA4DailyMetrics.date >= start,
            GA4DailyMetrics.date <= end,
            GA4DailyMetrics.dimension_hash == "base",
        )
    )
    return float(result.scalar() or 0)


def _severity(abs_pct: float) -> str:
    if abs_pct >= 75:
        return "high"
    if abs_pct >= 40:
        return "medium"
    return "low"


async def detect_metric_trends(
    db: AsyncSession,
    property_id: int,
    window_days: int = _WINDOW_DAYS,
) -> dict[str, Any] | None:
    """Compare last N days to prior N days. Flag metrics that moved past threshold."""
    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=window_days - 1)
    prior_end = start - timedelta(days=1)
    prior_start = prior_end - timedelta(days=window_days - 1)

    findings: list[dict[str, Any]] = []
    for column_name, display_name, min_baseline in _METRICS:
        current = await _sum_metric(db, property_id, column_name, start, end)
        prior = await _sum_metric(db, property_id, column_name, prior_start, prior_end)

        prior_daily_avg = prior / window_days if window_days else 0
        if prior_daily_avg < min_baseline:
            continue
        if prior == 0:
            continue

        delta_pct = (current - prior) / prior * 100
        if abs(delta_pct) < _DELTA_THRESHOLD_PCT:
            continue

        findings.append({
            "metric": display_name,
            "column": column_name,
            "current_total": round(current, 2),
            "prior_total": round(prior, 2),
            "delta_percent": round(delta_pct, 2),
            "direction": "up" if delta_pct > 0 else "down",
        })

    if not findings:
        logger.info("No significant trends detected", property_id=property_id)
        return None

    findings.sort(key=lambda f: abs(f["delta_percent"]), reverse=True)
    max_abs_pct = max(abs(f["delta_percent"]) for f in findings)
    return {
        "kind": "trend",
        "severity": _severity(max_abs_pct),
        "period_start": start,
        "period_end": end,
        "top_findings": findings,
        "total_count": len(findings),
        "context": {
            "window_days": window_days,
            "compared_to": "previous_period",
            "delta_threshold_pct": _DELTA_THRESHOLD_PCT,
        },
        # Stable identity = which metrics + their directions
        # (a 25%-down trend on Sessions IS the same "thing" today and tomorrow
        # unless the metric or direction changes).
        "content_identity": sorted(f"{f['metric']}:{f['direction']}" for f in findings),
    }
