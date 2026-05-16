from __future__ import annotations

from datetime import date
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
from prism.ai.tools.schemas import ComparePeriodsInput, DateRangeInput, QueryGA4Input

# ---------------------------------------------------------------------------
# Metric → column name mappings per table
# ---------------------------------------------------------------------------

_DAILY_METRICS_COLS: dict[str, str] = {
    "sessions": "sessions",
    "users": "users",
    "newUsers": "new_users",
    "new_users": "new_users",
    "engagedSessions": "engaged_sessions",
    "engaged_sessions": "engaged_sessions",
    "engagementRate": "engagement_rate",
    "engagement_rate": "engagement_rate",
    "averageSessionDuration": "average_session_duration",
    "average_session_duration": "average_session_duration",
    "bounceRate": "bounce_rate",
    "bounce_rate": "bounce_rate",
    "screenPageViews": "screen_page_views",
    "screen_page_views": "screen_page_views",
    "conversions": "conversions",
    "totalRevenue": "total_revenue",
    "total_revenue": "total_revenue",
}

_LP_METRICS_COLS: dict[str, str] = {
    "sessions": "sessions",
    "users": "users",
    "conversions": "conversions",
    "revenue": "revenue",
    "bounceRate": "bounce_rate",
    "bounce_rate": "bounce_rate",
}

_TS_METRICS_COLS: dict[str, str] = {
    "sessions": "sessions",
    "users": "users",
    "conversions": "conversions",
}

_DEV_METRICS_COLS: dict[str, str] = {
    "sessions": "sessions",
    "users": "users",
    "conversions": "conversions",
}

_GEO_METRICS_COLS: dict[str, str] = {
    "sessions": "sessions",
    "users": "users",
}

_EVT_METRICS_COLS: dict[str, str] = {
    "eventCount": "event_count",
    "event_count": "event_count",
    "conversions": "conversions",
}

_CHAN_METRICS_COLS: dict[str, str] = {
    "sessions": "sessions",
    "users": "users",
    "conversions": "conversions",
    "totalRevenue": "total_revenue",
    "total_revenue": "total_revenue",
}

_UTYPE_METRICS_COLS: dict[str, str] = {
    "sessions": "sessions",
    "users": "users",
    "engagedSessions": "engaged_sessions",
    "engaged_sessions": "engaged_sessions",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_date(d: str) -> date:
    return date.fromisoformat(d)


def _compute_tail_summary(all_values: list[float]) -> dict[str, Any]:
    """Compute simple stats for truncated tail rows."""
    if not all_values:
        return {"row_count": 0, "sum": 0.0, "mean": 0.0, "p50": 0.0}
    sorted_vals = sorted(all_values)
    n = len(sorted_vals)
    total = sum(sorted_vals)
    mean = total / n
    mid = n // 2
    p50 = sorted_vals[mid] if n % 2 == 1 else (sorted_vals[mid - 1] + sorted_vals[mid]) / 2
    return {"row_count": n, "sum": round(total, 4), "mean": round(mean, 4), "p50": round(p50, 4)}


def _row_to_dict(row: Any, columns: list[str]) -> dict[str, Any]:
    return {col: getattr(row, col, None) for col in columns}


# ---------------------------------------------------------------------------
# query_ga4
# ---------------------------------------------------------------------------

async def query_ga4(inp: QueryGA4Input, db: AsyncSession) -> dict[str, Any]:
    start = _parse_date(inp.date_range.start)
    end = _parse_date(inp.date_range.end)
    dims = inp.dimensions or []

    # Determine which table to use based on dimensions
    primary_dim = dims[0] if dims else None

    if not dims or dims == ["date"]:
        return await _query_daily_metrics(inp, db, start, end)
    elif primary_dim == "landingPage":
        return await _query_landing_pages(inp, db, start, end)
    elif primary_dim == "deviceCategory":
        return await _query_devices(inp, db, start, end)
    elif primary_dim in ("sessionSource", "sessionMedium"):
        return await _query_traffic_sources(inp, db, start, end)
    elif primary_dim == "country":
        return await _query_geo(inp, db, start, end)
    elif primary_dim == "eventName":
        return await _query_events(inp, db, start, end)
    elif primary_dim == "sessionDefaultChannelGroup":
        return await _query_channels(inp, db, start, end)
    elif primary_dim == "newVsReturning":
        return await _query_user_type(inp, db, start, end)
    else:
        return {
            "error": f"unsupported dimension: {primary_dim!r}",
            "rows": [],
            "truncated": False,
            "tail_summary": None,
            "row_count": 0,
            "query_info": {
                "table": "unknown",
                "date_range": {"start": inp.date_range.start, "end": inp.date_range.end},
                "metrics": inp.metrics,
                "dimensions": dims,
            },
        }


async def _query_daily_metrics(
    inp: QueryGA4Input, db: AsyncSession, start: date, end: date
) -> dict[str, Any]:
    valid_cols = [_DAILY_METRICS_COLS.get(m) for m in inp.metrics]
    valid_cols = [c for c in valid_cols if c is not None]
    if not valid_cols:
        valid_cols = ["sessions"]

    stmt = (
        select(GA4DailyMetrics)
        .where(
            GA4DailyMetrics.property_id == inp.property_id,
            GA4DailyMetrics.date >= start,
            GA4DailyMetrics.date <= end,
        )
        .order_by(GA4DailyMetrics.date)
    )

    result = await db.execute(stmt)
    rows_raw = result.scalars().all()

    output_cols = ["date"] + valid_cols
    rows = [_row_to_dict(r, output_cols) for r in rows_raw]
    # Normalise date to str
    for row in rows:
        if isinstance(row.get("date"), date):
            row["date"] = row["date"].isoformat()

    return _apply_cap_and_sort(rows, valid_cols[0], inp.limit, inp.sort_by, "ga4_daily_metrics", inp)


async def _query_landing_pages(
    inp: QueryGA4Input, db: AsyncSession, start: date, end: date
) -> dict[str, Any]:
    valid_cols = [_LP_METRICS_COLS.get(m) for m in inp.metrics]
    valid_cols = [c for c in valid_cols if c is not None]
    if not valid_cols:
        valid_cols = ["sessions"]

    stmt = (
        select(
            GA4LandingPagesDaily.landing_page,
            func.sum(GA4LandingPagesDaily.sessions).label("sessions"),
            func.sum(GA4LandingPagesDaily.users).label("users"),
            func.sum(GA4LandingPagesDaily.conversions).label("conversions"),
            func.sum(GA4LandingPagesDaily.revenue).label("revenue"),
            func.avg(GA4LandingPagesDaily.bounce_rate).label("bounce_rate"),
        )
        .where(
            GA4LandingPagesDaily.property_id == inp.property_id,
            GA4LandingPagesDaily.date >= start,
            GA4LandingPagesDaily.date <= end,
        )
        .group_by(GA4LandingPagesDaily.landing_page)
    )

    result = await db.execute(stmt)
    rows_raw = result.mappings().all()
    rows = [dict(r) for r in rows_raw]

    primary_col = valid_cols[0]
    return _apply_cap_and_sort(rows, primary_col, inp.limit, inp.sort_by, "ga4_landing_pages_daily", inp)


async def _query_traffic_sources(
    inp: QueryGA4Input, db: AsyncSession, start: date, end: date
) -> dict[str, Any]:
    valid_cols = [_TS_METRICS_COLS.get(m) for m in inp.metrics]
    valid_cols = [c for c in valid_cols if c is not None]
    if not valid_cols:
        valid_cols = ["sessions"]

    stmt = (
        select(
            GA4TrafficSourcesDaily.source,
            GA4TrafficSourcesDaily.medium,
            GA4TrafficSourcesDaily.campaign,
            func.sum(GA4TrafficSourcesDaily.sessions).label("sessions"),
            func.sum(GA4TrafficSourcesDaily.users).label("users"),
            func.sum(GA4TrafficSourcesDaily.conversions).label("conversions"),
        )
        .where(
            GA4TrafficSourcesDaily.property_id == inp.property_id,
            GA4TrafficSourcesDaily.date >= start,
            GA4TrafficSourcesDaily.date <= end,
        )
        .group_by(
            GA4TrafficSourcesDaily.source,
            GA4TrafficSourcesDaily.medium,
            GA4TrafficSourcesDaily.campaign,
        )
    )

    result = await db.execute(stmt)
    rows_raw = result.mappings().all()
    rows = [dict(r) for r in rows_raw]

    primary_col = valid_cols[0]
    return _apply_cap_and_sort(rows, primary_col, inp.limit, inp.sort_by, "ga4_traffic_sources_daily", inp)


async def _query_devices(
    inp: QueryGA4Input, db: AsyncSession, start: date, end: date
) -> dict[str, Any]:
    valid_cols = [_DEV_METRICS_COLS.get(m) for m in inp.metrics]
    valid_cols = [c for c in valid_cols if c is not None]
    if not valid_cols:
        valid_cols = ["sessions"]

    stmt = (
        select(
            GA4DevicesDaily.device_category,
            func.sum(GA4DevicesDaily.sessions).label("sessions"),
            func.sum(GA4DevicesDaily.users).label("users"),
            func.sum(GA4DevicesDaily.conversions).label("conversions"),
        )
        .where(
            GA4DevicesDaily.property_id == inp.property_id,
            GA4DevicesDaily.date >= start,
            GA4DevicesDaily.date <= end,
        )
        .group_by(GA4DevicesDaily.device_category)
    )

    result = await db.execute(stmt)
    rows_raw = result.mappings().all()
    rows = [dict(r) for r in rows_raw]

    primary_col = valid_cols[0]
    return _apply_cap_and_sort(rows, primary_col, inp.limit, inp.sort_by, "ga4_devices_daily", inp)


async def _query_geo(
    inp: QueryGA4Input, db: AsyncSession, start: date, end: date
) -> dict[str, Any]:
    valid_cols = [_GEO_METRICS_COLS.get(m) for m in inp.metrics]
    valid_cols = [c for c in valid_cols if c is not None]
    if not valid_cols:
        valid_cols = ["sessions"]

    stmt = (
        select(
            GA4GeoDaily.country,
            func.sum(GA4GeoDaily.sessions).label("sessions"),
            func.sum(GA4GeoDaily.users).label("users"),
        )
        .where(
            GA4GeoDaily.property_id == inp.property_id,
            GA4GeoDaily.date >= start,
            GA4GeoDaily.date <= end,
        )
        .group_by(GA4GeoDaily.country)
    )

    result = await db.execute(stmt)
    rows_raw = result.mappings().all()
    rows = [dict(r) for r in rows_raw]

    primary_col = valid_cols[0]
    return _apply_cap_and_sort(rows, primary_col, inp.limit, inp.sort_by, "ga4_geo_daily", inp)


async def _query_events(
    inp: QueryGA4Input, db: AsyncSession, start: date, end: date
) -> dict[str, Any]:
    valid_cols = [_EVT_METRICS_COLS.get(m) for m in inp.metrics]
    valid_cols = [c for c in valid_cols if c is not None]
    if not valid_cols:
        valid_cols = ["event_count"]

    stmt = (
        select(
            GA4EventsDaily.event_name,
            func.sum(GA4EventsDaily.event_count).label("event_count"),
            func.sum(GA4EventsDaily.conversions).label("conversions"),
        )
        .where(
            GA4EventsDaily.property_id == inp.property_id,
            GA4EventsDaily.date >= start,
            GA4EventsDaily.date <= end,
        )
        .group_by(GA4EventsDaily.event_name)
    )

    result = await db.execute(stmt)
    rows_raw = result.mappings().all()
    rows = [dict(r) for r in rows_raw]

    primary_col = valid_cols[0]
    return _apply_cap_and_sort(rows, primary_col, inp.limit, inp.sort_by, "ga4_events_daily", inp)


async def _query_channels(
    inp: QueryGA4Input, db: AsyncSession, start: date, end: date
) -> dict[str, Any]:
    valid_cols = [_CHAN_METRICS_COLS.get(m) for m in inp.metrics]
    valid_cols = [c for c in valid_cols if c is not None]
    if not valid_cols:
        valid_cols = ["sessions"]

    stmt = (
        select(
            GA4ChannelsDaily.channel_group,
            func.sum(GA4ChannelsDaily.sessions).label("sessions"),
            func.sum(GA4ChannelsDaily.users).label("users"),
            func.sum(GA4ChannelsDaily.conversions).label("conversions"),
            func.sum(GA4ChannelsDaily.total_revenue).label("total_revenue"),
        )
        .where(
            GA4ChannelsDaily.property_id == inp.property_id,
            GA4ChannelsDaily.date >= start,
            GA4ChannelsDaily.date <= end,
        )
        .group_by(GA4ChannelsDaily.channel_group)
    )

    result = await db.execute(stmt)
    rows_raw = result.mappings().all()
    rows = [dict(r) for r in rows_raw]

    primary_col = valid_cols[0]
    return _apply_cap_and_sort(rows, primary_col, inp.limit, inp.sort_by, "ga4_channels_daily", inp)


async def _query_user_type(
    inp: QueryGA4Input, db: AsyncSession, start: date, end: date
) -> dict[str, Any]:
    valid_cols = [_UTYPE_METRICS_COLS.get(m) for m in inp.metrics]
    valid_cols = [c for c in valid_cols if c is not None]
    if not valid_cols:
        valid_cols = ["sessions"]

    stmt = (
        select(
            GA4UserTypeDaily.user_type,
            func.sum(GA4UserTypeDaily.sessions).label("sessions"),
            func.sum(GA4UserTypeDaily.users).label("users"),
            func.sum(GA4UserTypeDaily.engaged_sessions).label("engaged_sessions"),
        )
        .where(
            GA4UserTypeDaily.property_id == inp.property_id,
            GA4UserTypeDaily.date >= start,
            GA4UserTypeDaily.date <= end,
        )
        .group_by(GA4UserTypeDaily.user_type)
    )

    result = await db.execute(stmt)
    rows_raw = result.mappings().all()
    rows = [dict(r) for r in rows_raw]

    primary_col = valid_cols[0]
    return _apply_cap_and_sort(rows, primary_col, inp.limit, inp.sort_by, "ga4_user_type_daily", inp)


# ---------------------------------------------------------------------------
# Row cap and sorting helper
# ---------------------------------------------------------------------------

def _apply_cap_and_sort(
    rows: list[dict[str, Any]],
    primary_col: str,
    limit: int,
    sort_by: str | None,
    table: str,
    inp: QueryGA4Input | None = None,
) -> dict[str, Any]:
    sort_col = sort_by or primary_col

    def sort_key(r: dict[str, Any]) -> float:
        v = r.get(sort_col, 0)
        try:
            return float(v) if v is not None else 0.0
        except (TypeError, ValueError):
            return 0.0

    rows.sort(key=sort_key, reverse=True)
    total = len(rows)
    truncated = total > limit
    tail_summary: dict[str, Any] | None = None

    if truncated:
        tail_rows = rows[limit:]
        tail_vals = [sort_key(r) for r in tail_rows]
        tail_summary = _compute_tail_summary(tail_vals)
        rows = rows[:limit]

    query_info: dict[str, Any] = {"table": table}
    if inp is not None:
        query_info.update({
            "date_range": {"start": inp.date_range.start, "end": inp.date_range.end},
            "metrics": inp.metrics,
            "dimensions": inp.dimensions,
        })

    return {
        "rows": rows,
        "truncated": truncated,
        "tail_summary": tail_summary,
        "row_count": total,
        "query_info": query_info,
    }


# ---------------------------------------------------------------------------
# compare_periods
# ---------------------------------------------------------------------------

async def compare_periods(inp: ComparePeriodsInput, db: AsyncSession) -> dict[str, Any]:
    from prism.ai.tools.schemas import QueryGA4Input, QueryGSCInput

    if inp.source == "ga4":
        inp_a = QueryGA4Input(
            property_id=inp.property_id,
            date_range=inp.period_a,
            metrics=[inp.metric],
            dimensions=inp.dimensions,
            filters=inp.filters,
            limit=1000,
        )
        inp_b = QueryGA4Input(
            property_id=inp.property_id,
            date_range=inp.period_b,
            metrics=[inp.metric],
            dimensions=inp.dimensions,
            filters=inp.filters,
            limit=1000,
        )
        result_a = await query_ga4(inp_a, db)
        result_b = await query_ga4(inp_b, db)
    else:
        from prism.ai.tools.gsc_tools import query_gsc

        inp_a = QueryGSCInput(
            property_id=inp.property_id,
            date_range=inp.period_a,
            dimensions=inp.dimensions or ["date"],
            filters=inp.filters,
            limit=1000,
        )
        inp_b = QueryGSCInput(
            property_id=inp.property_id,
            date_range=inp.period_b,
            dimensions=inp.dimensions or ["date"],
            filters=inp.filters,
            limit=1000,
        )
        result_a = await query_gsc(inp_a, db)
        result_b = await query_gsc(inp_b, db)

    # Map friendly metric name to potential column names
    metric_col = _DAILY_METRICS_COLS.get(inp.metric, inp.metric)

    def _sum_metric(rows: list[dict[str, Any]], col: str) -> float:
        total = 0.0
        for row in rows:
            v = row.get(col, row.get(inp.metric, 0))
            try:
                total += float(v) if v is not None else 0.0
            except (TypeError, ValueError):
                pass
        return total

    total_a = _sum_metric(result_a.get("rows", []), metric_col)
    total_b = _sum_metric(result_b.get("rows", []), metric_col)

    delta_abs = total_b - total_a
    delta_pct = ((total_b - total_a) / total_a * 100) if total_a != 0 else (100.0 if total_b > 0 else 0.0)

    return {
        "period_a": {
            "date_range": {"start": inp.period_a.start, "end": inp.period_a.end},
            "total": round(total_a, 4),
            "rows": result_a.get("rows", []),
        },
        "period_b": {
            "date_range": {"start": inp.period_b.start, "end": inp.period_b.end},
            "total": round(total_b, 4),
            "rows": result_b.get("rows", []),
        },
        "delta_pct": round(delta_pct, 2),
        "delta_abs": round(delta_abs, 4),
        "metric": inp.metric,
    }
