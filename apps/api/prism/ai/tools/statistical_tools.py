from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from prism.db.models.ga4 import (
    GA4ChannelsDaily,
    GA4DailyMetrics,
    GA4DevicesDaily,
    GA4EventsDaily,
    GA4GeoDaily,
    GA4LandingPagesDaily,
    GA4TrafficSourcesDaily,
    GA4UserTypeDaily,
)
from prism.db.models.gsc import (
    GSCAppearanceDaily,
    GSCPagesDaily,
    GSCQueriesDaily,
    GSCSearchTypeDaily,
)
from prism.ai.tools.schemas import DetectAnomaliesInput, RollingTrendInput, SegmentSplitInput


# ---------------------------------------------------------------------------
# Metric → (table, column) routing
# ---------------------------------------------------------------------------

_GA4_METRIC_MAP: dict[str, tuple[Any, str]] = {
    "sessions": (GA4DailyMetrics, "sessions"),
    "users": (GA4DailyMetrics, "users"),
    "newUsers": (GA4DailyMetrics, "new_users"),
    "new_users": (GA4DailyMetrics, "new_users"),
    "engagedSessions": (GA4DailyMetrics, "engaged_sessions"),
    "engaged_sessions": (GA4DailyMetrics, "engaged_sessions"),
    "bounceRate": (GA4DailyMetrics, "bounce_rate"),
    "bounce_rate": (GA4DailyMetrics, "bounce_rate"),
    "screenPageViews": (GA4DailyMetrics, "screen_page_views"),
    "screen_page_views": (GA4DailyMetrics, "screen_page_views"),
    "conversions": (GA4DailyMetrics, "conversions"),
    "totalRevenue": (GA4DailyMetrics, "total_revenue"),
    "total_revenue": (GA4DailyMetrics, "total_revenue"),
    "engagementRate": (GA4DailyMetrics, "engagement_rate"),
    "engagement_rate": (GA4DailyMetrics, "engagement_rate"),
    "averageSessionDuration": (GA4DailyMetrics, "average_session_duration"),
    "average_session_duration": (GA4DailyMetrics, "average_session_duration"),
}

_GSC_METRIC_MAP: dict[str, str] = {
    "clicks": "clicks",
    "impressions": "impressions",
    "ctr": "ctr",
    "position": "position",
    "avg_position": "position",
}

# Dimension → (table, dimension_col, metric_cols) for segment_split
_GA4_DIM_MAP: dict[str, tuple[Any, str, list[str]]] = {
    "landingPage": (GA4LandingPagesDaily, "landing_page", ["sessions", "users", "conversions", "revenue", "bounce_rate"]),
    "deviceCategory": (GA4DevicesDaily, "device_category", ["sessions", "users", "conversions"]),
    "sessionSource": (GA4TrafficSourcesDaily, "source", ["sessions", "users", "conversions"]),
    "sessionMedium": (GA4TrafficSourcesDaily, "medium", ["sessions", "users", "conversions"]),
    "country": (GA4GeoDaily, "country", ["sessions", "users"]),
    "eventName": (GA4EventsDaily, "event_name", ["event_count", "conversions"]),
    "sessionDefaultChannelGroup": (GA4ChannelsDaily, "channel_group", ["sessions", "users", "conversions", "total_revenue"]),
    "newVsReturning": (GA4UserTypeDaily, "user_type", ["sessions", "users", "engaged_sessions"]),
}

_GSC_DIM_MAP: dict[str, tuple[Any, str, list[str]]] = {
    "query": (GSCQueriesDaily, "query", ["clicks", "impressions"]),
    "page": (GSCPagesDaily, "page", ["clicks", "impressions"]),
    "searchAppearance": (GSCAppearanceDaily, "search_appearance", ["clicks", "impressions"]),
    "searchType": (GSCSearchTypeDaily, "search_type", ["clicks", "impressions"]),
}


# ---------------------------------------------------------------------------
# detect_anomalies
# ---------------------------------------------------------------------------

async def detect_anomalies(inp: DetectAnomaliesInput, db: AsyncSession) -> dict[str, Any]:
    import pandas as pd

    end = date.today()
    start = end - timedelta(days=inp.lookback_days - 1)

    series = await _fetch_daily_series(inp.source, inp.metric, inp.property_id, start, end, db)

    if not series:
        return {
            "anomalies": [],
            "metric": inp.metric,
            "lookback_days": inp.lookback_days,
        }

    df = pd.DataFrame(series, columns=["date", "value"])
    df = df.sort_values("date").reset_index(drop=True)
    df["value"] = df["value"].fillna(0.0).astype(float)

    window = min(7, len(df))
    df["rolling_mean"] = df["value"].rolling(window=window, min_periods=1).mean()
    df["rolling_std"] = df["value"].rolling(window=window, min_periods=1).std().fillna(0.0)
    df["z_score"] = df.apply(
        lambda r: (r["value"] - r["rolling_mean"]) / r["rolling_std"]
        if r["rolling_std"] > 0 else 0.0,
        axis=1,
    )

    anomalies: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        z = float(row["z_score"])
        if abs(z) >= inp.z_threshold:
            anomalies.append({
                "date": str(row["date"]),
                "value": round(float(row["value"]), 4),
                "z_score": round(z, 3),
                "direction": "up" if z > 0 else "down",
                "rolling_mean": round(float(row["rolling_mean"]), 4),
            })

    return {
        "anomalies": anomalies,
        "metric": inp.metric,
        "lookback_days": inp.lookback_days,
    }


# ---------------------------------------------------------------------------
# rolling_trend
# ---------------------------------------------------------------------------

async def rolling_trend(inp: RollingTrendInput, db: AsyncSession) -> dict[str, Any]:
    import pandas as pd

    end = date.today()
    start = end - timedelta(days=inp.lookback_days - 1)

    series = await _fetch_daily_series(inp.source, inp.metric, inp.property_id, start, end, db)

    if not series:
        return {"trend": [], "window_days": inp.window_days}

    df = pd.DataFrame(series, columns=["date", "value"])
    df = df.sort_values("date").reset_index(drop=True)
    df["value"] = df["value"].fillna(0.0).astype(float)
    df["rolling_avg"] = df["value"].rolling(window=inp.window_days, min_periods=1).mean()
    df["delta_pct"] = df["rolling_avg"].pct_change() * 100

    trend: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        delta = float(row["delta_pct"]) if not pd.isna(row["delta_pct"]) else None
        trend.append({
            "date": str(row["date"]),
            "value": round(float(row["value"]), 4),
            "rolling_avg": round(float(row["rolling_avg"]), 4),
            "delta_pct": round(delta, 2) if delta is not None else None,
        })

    return {"trend": trend, "window_days": inp.window_days}


# ---------------------------------------------------------------------------
# segment_split
# ---------------------------------------------------------------------------

async def segment_split(inp: SegmentSplitInput, db: AsyncSession) -> dict[str, Any]:
    start_dt = date.fromisoformat(inp.date_range.start)
    end_dt = date.fromisoformat(inp.date_range.end)

    rows = await _fetch_segment_rows(inp.source, inp.metric, inp.dimension, inp.property_id, start_dt, end_dt, db)

    if not rows:
        return {
            "total": 0.0,
            "pareto_80_count": 0,
            "items": [],
            "truncated": False,
        }

    rows.sort(key=lambda x: x[1], reverse=True)
    total = sum(v for _, v in rows)

    items: list[dict[str, Any]] = []
    cumulative = 0.0
    pareto_count = 0
    pareto_reached = False

    for dim_val, val in rows:
        share = (val / total * 100) if total > 0 else 0.0
        cumulative += share
        if not pareto_reached and cumulative >= 80.0:
            pareto_count = len(items) + 1
            pareto_reached = True
        items.append({
            "dimension_value": str(dim_val),
            "value": round(float(val), 4),
            "share_pct": round(share, 2),
            "cumulative_pct": round(cumulative, 2),
        })

    if not pareto_reached:
        pareto_count = len(items)

    truncated = len(rows) > 500
    if truncated:
        items = items[:500]

    return {
        "total": round(total, 4),
        "pareto_80_count": pareto_count,
        "items": items,
        "truncated": truncated,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

async def _fetch_daily_series(
    source: str,
    metric: str,
    property_id: int,
    start: date,
    end: date,
    db: AsyncSession,
) -> list[tuple[str, float]]:
    """Return [(date_str, value)] for the requested metric."""
    if source == "ga4":
        info = _GA4_METRIC_MAP.get(metric)
        if not info:
            return []
        table, col = info
        col_attr = getattr(table, col)
        stmt = (
            select(table.date, func.sum(col_attr).label("value"))
            .where(table.property_id == property_id, table.date >= start, table.date <= end)
            .group_by(table.date)
            .order_by(table.date)
        )
    else:
        # GSC: aggregate gsc_queries_daily
        gsc_col = _GSC_METRIC_MAP.get(metric)
        if not gsc_col:
            return []
        col_attr = getattr(GSCQueriesDaily, gsc_col)
        if gsc_col in ("ctr", "position"):
            agg = func.avg(col_attr)
        else:
            agg = func.sum(col_attr)
        stmt = (
            select(GSCQueriesDaily.date, agg.label("value"))
            .where(
                GSCQueriesDaily.property_id == property_id,
                GSCQueriesDaily.date >= start,
                GSCQueriesDaily.date <= end,
            )
            .group_by(GSCQueriesDaily.date)
            .order_by(GSCQueriesDaily.date)
        )

    result = await db.execute(stmt)
    return [(str(r.date), float(r.value or 0)) for r in result]


async def _fetch_segment_rows(
    source: str,
    metric: str,
    dimension: str,
    property_id: int,
    start: date,
    end: date,
    db: AsyncSession,
) -> list[tuple[Any, float]]:
    """Return [(dimension_value, aggregated_metric_value)] for segment_split."""
    if source == "ga4":
        dim_info = _GA4_DIM_MAP.get(dimension)
        if not dim_info:
            return []
        table, dim_col_name, available_metrics = dim_info
        dim_col = getattr(table, dim_col_name)

        # Find actual DB column for requested metric
        metric_col_name: str | None = None
        for m in [metric] + list(_GA4_METRIC_MAP.keys()):
            if m == metric:
                info = _GA4_METRIC_MAP.get(m)
                if info:
                    _, candidate = info
                    if hasattr(table, candidate):
                        metric_col_name = candidate
                        break
        if not metric_col_name:
            # Try direct match on table
            for col_name in available_metrics:
                if col_name == metric or col_name.replace("_", "") == metric.lower().replace("_", ""):
                    metric_col_name = col_name
                    break
        if not metric_col_name:
            metric_col_name = available_metrics[0]

        metric_col = getattr(table, metric_col_name)
        # Use avg for rates, sum for counts
        is_rate = metric_col_name in ("bounce_rate", "engagement_rate", "average_session_duration", "avg_session_duration")
        agg = func.avg(metric_col) if is_rate else func.sum(metric_col)

        stmt = (
            select(dim_col.label("dimension_value"), agg.label("value"))
            .where(table.property_id == property_id, table.date >= start, table.date <= end)
            .group_by(dim_col)
        )
        result = await db.execute(stmt)
        return [(r.dimension_value, float(r.value or 0)) for r in result]

    else:
        # GSC
        dim_info_gsc = _GSC_DIM_MAP.get(dimension)
        if not dim_info_gsc:
            return []
        table, dim_col_name, available_metrics = dim_info_gsc
        dim_col = getattr(table, dim_col_name)

        gsc_col = _GSC_METRIC_MAP.get(metric, metric)
        if not hasattr(table, gsc_col):
            gsc_col = available_metrics[0]

        metric_col = getattr(table, gsc_col)
        is_avg = gsc_col in ("ctr", "position")
        agg = func.avg(metric_col) if is_avg else func.sum(metric_col)

        stmt = (
            select(dim_col.label("dimension_value"), agg.label("value"))
            .where(table.property_id == property_id, table.date >= start, table.date <= end)
            .group_by(dim_col)
        )
        result = await db.execute(stmt)
        return [(r.dimension_value, float(r.value or 0)) for r in result]
