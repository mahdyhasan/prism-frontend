"""CSV export helpers — aggregate warehouse rows by their natural grain
and return UTF-8 CSV bodies as strings.

These helpers are intentionally thin: each one selects from a single
warehouse table for a property/date range, aggregates by the table's
non-date dimensions (or just by date for daily metrics), and writes a
CSV with a header row plus rows ordered by sessions/clicks descending.
"""
from __future__ import annotations

import csv
import io
from datetime import date

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from prism.db.models.ga4 import (
    GA4DailyMetrics,
    GA4DevicesDaily,
    GA4GeoDaily,
    GA4LandingPagesDaily,
    GA4TrafficSourcesDaily,
)
from prism.db.models.gsc import GSCPagesDaily, GSCQueriesDaily


def _writer() -> tuple[io.StringIO, "csv._writer"]:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    return buf, w


def _safe_div(num: float, denom: float) -> float:
    return num / denom if denom else 0.0


# ── GA4 ───────────────────────────────────────────────────────────────────────


async def export_ga4_daily_metrics_csv(
    db: AsyncSession,
    property_id: int,
    start: date,
    end: date,
) -> str:
    """One row per day — top-level GA4 session metrics."""
    result = await db.execute(
        select(
            GA4DailyMetrics.date,
            func.sum(GA4DailyMetrics.sessions).label("sessions"),
            func.sum(GA4DailyMetrics.users).label("users"),
            func.sum(GA4DailyMetrics.new_users).label("new_users"),
            func.sum(GA4DailyMetrics.engaged_sessions).label("engaged_sessions"),
            func.avg(GA4DailyMetrics.engagement_rate).label("engagement_rate"),
            func.avg(GA4DailyMetrics.bounce_rate).label("bounce_rate"),
            func.avg(GA4DailyMetrics.average_session_duration).label("avg_session_duration"),
            func.sum(GA4DailyMetrics.screen_page_views).label("page_views"),
            func.sum(GA4DailyMetrics.conversions).label("conversions"),
            func.sum(GA4DailyMetrics.total_revenue).label("total_revenue"),
        )
        .where(
            GA4DailyMetrics.property_id == property_id,
            GA4DailyMetrics.date >= start,
            GA4DailyMetrics.date <= end,
            GA4DailyMetrics.dimension_hash == "base",
        )
        .group_by(GA4DailyMetrics.date)
        .order_by(GA4DailyMetrics.date)
    )

    buf, w = _writer()
    w.writerow([
        "date",
        "sessions",
        "users",
        "new_users",
        "engaged_sessions",
        "engagement_rate",
        "bounce_rate",
        "avg_session_duration",
        "page_views",
        "conversions",
        "total_revenue",
    ])
    for row in result.all():
        w.writerow([
            row.date.isoformat(),
            int(row.sessions or 0),
            int(row.users or 0),
            int(row.new_users or 0),
            int(row.engaged_sessions or 0),
            round(float(row.engagement_rate or 0), 6),
            round(float(row.bounce_rate or 0), 6),
            round(float(row.avg_session_duration or 0), 4),
            int(row.page_views or 0),
            int(row.conversions or 0),
            round(float(row.total_revenue or 0), 4),
        ])
    return buf.getvalue()


async def export_ga4_landing_pages_csv(
    db: AsyncSession,
    property_id: int,
    start: date,
    end: date,
) -> str:
    """One row per landing page, aggregated over the date range."""
    result = await db.execute(
        select(
            GA4LandingPagesDaily.landing_page,
            func.sum(GA4LandingPagesDaily.sessions).label("sessions"),
            func.sum(GA4LandingPagesDaily.users).label("users"),
            func.sum(GA4LandingPagesDaily.conversions).label("conversions"),
            func.sum(GA4LandingPagesDaily.revenue).label("revenue"),
            func.avg(GA4LandingPagesDaily.bounce_rate).label("bounce_rate"),
        )
        .where(
            GA4LandingPagesDaily.property_id == property_id,
            GA4LandingPagesDaily.date >= start,
            GA4LandingPagesDaily.date <= end,
        )
        .group_by(GA4LandingPagesDaily.landing_page)
        .order_by(text("sessions DESC"))
    )

    buf, w = _writer()
    w.writerow(["landing_page", "sessions", "users", "conversions", "revenue", "bounce_rate"])
    for row in result.all():
        w.writerow([
            row.landing_page,
            int(row.sessions or 0),
            int(row.users or 0),
            int(row.conversions or 0),
            round(float(row.revenue or 0), 4),
            round(float(row.bounce_rate or 0), 6),
        ])
    return buf.getvalue()


async def export_ga4_traffic_sources_csv(
    db: AsyncSession,
    property_id: int,
    start: date,
    end: date,
) -> str:
    """One row per source/medium/campaign tuple, aggregated over the date range."""
    result = await db.execute(
        select(
            GA4TrafficSourcesDaily.source,
            GA4TrafficSourcesDaily.medium,
            GA4TrafficSourcesDaily.campaign,
            func.sum(GA4TrafficSourcesDaily.sessions).label("sessions"),
            func.sum(GA4TrafficSourcesDaily.users).label("users"),
            func.sum(GA4TrafficSourcesDaily.conversions).label("conversions"),
        )
        .where(
            GA4TrafficSourcesDaily.property_id == property_id,
            GA4TrafficSourcesDaily.date >= start,
            GA4TrafficSourcesDaily.date <= end,
        )
        .group_by(
            GA4TrafficSourcesDaily.source,
            GA4TrafficSourcesDaily.medium,
            GA4TrafficSourcesDaily.campaign,
        )
        .order_by(text("sessions DESC"))
    )

    buf, w = _writer()
    w.writerow(["source", "medium", "campaign", "sessions", "users", "conversions"])
    for row in result.all():
        w.writerow([
            row.source,
            row.medium,
            row.campaign,
            int(row.sessions or 0),
            int(row.users or 0),
            int(row.conversions or 0),
        ])
    return buf.getvalue()


async def export_ga4_devices_csv(
    db: AsyncSession,
    property_id: int,
    start: date,
    end: date,
) -> str:
    """One row per device category, aggregated over the date range."""
    result = await db.execute(
        select(
            GA4DevicesDaily.device_category,
            func.sum(GA4DevicesDaily.sessions).label("sessions"),
            func.sum(GA4DevicesDaily.users).label("users"),
            func.sum(GA4DevicesDaily.conversions).label("conversions"),
        )
        .where(
            GA4DevicesDaily.property_id == property_id,
            GA4DevicesDaily.date >= start,
            GA4DevicesDaily.date <= end,
        )
        .group_by(GA4DevicesDaily.device_category)
        .order_by(text("sessions DESC"))
    )

    buf, w = _writer()
    w.writerow(["device_category", "sessions", "users", "conversions"])
    for row in result.all():
        w.writerow([
            row.device_category,
            int(row.sessions or 0),
            int(row.users or 0),
            int(row.conversions or 0),
        ])
    return buf.getvalue()


async def export_ga4_geo_csv(
    db: AsyncSession,
    property_id: int,
    start: date,
    end: date,
) -> str:
    """One row per country/region, aggregated over the date range."""
    result = await db.execute(
        select(
            GA4GeoDaily.country,
            GA4GeoDaily.region,
            func.sum(GA4GeoDaily.sessions).label("sessions"),
            func.sum(GA4GeoDaily.users).label("users"),
        )
        .where(
            GA4GeoDaily.property_id == property_id,
            GA4GeoDaily.date >= start,
            GA4GeoDaily.date <= end,
        )
        .group_by(GA4GeoDaily.country, GA4GeoDaily.region)
        .order_by(text("sessions DESC"))
    )

    buf, w = _writer()
    w.writerow(["country", "region", "sessions", "users"])
    for row in result.all():
        w.writerow([
            row.country,
            row.region,
            int(row.sessions or 0),
            int(row.users or 0),
        ])
    return buf.getvalue()


# ── GSC ───────────────────────────────────────────────────────────────────────


async def export_gsc_queries_csv(
    db: AsyncSession,
    property_id: int,
    start: date,
    end: date,
) -> str:
    """One row per search query, aggregated over the date range.

    CTR is computed from total clicks / impressions; position is impression-weighted.
    """
    impressions_sum = func.sum(GSCQueriesDaily.impressions)
    clicks_sum = func.sum(GSCQueriesDaily.clicks)
    weighted_position = func.sum(GSCQueriesDaily.position * GSCQueriesDaily.impressions)

    result = await db.execute(
        select(
            GSCQueriesDaily.query.label("query"),
            clicks_sum.label("clicks"),
            impressions_sum.label("impressions"),
            weighted_position.label("weighted_position"),
        )
        .where(
            GSCQueriesDaily.property_id == property_id,
            GSCQueriesDaily.date >= start,
            GSCQueriesDaily.date <= end,
        )
        .group_by(GSCQueriesDaily.query)
        .order_by(text("clicks DESC"))
    )

    buf, w = _writer()
    w.writerow(["query", "clicks", "impressions", "ctr", "position"])
    for r in result.all():
        clicks = float(r.clicks or 0)
        impressions = float(r.impressions or 0)
        ctr = _safe_div(clicks, impressions)
        position = _safe_div(float(r.weighted_position or 0), impressions)
        w.writerow([
            r.query,
            int(clicks),
            int(impressions),
            round(ctr, 6),
            round(position, 2),
        ])
    return buf.getvalue()


async def export_gsc_pages_csv(
    db: AsyncSession,
    property_id: int,
    start: date,
    end: date,
) -> str:
    """One row per landing page, aggregated over the date range."""
    impressions_sum = func.sum(GSCPagesDaily.impressions)
    clicks_sum = func.sum(GSCPagesDaily.clicks)
    weighted_position = func.sum(GSCPagesDaily.position * GSCPagesDaily.impressions)

    result = await db.execute(
        select(
            GSCPagesDaily.page.label("page"),
            clicks_sum.label("clicks"),
            impressions_sum.label("impressions"),
            weighted_position.label("weighted_position"),
        )
        .where(
            GSCPagesDaily.property_id == property_id,
            GSCPagesDaily.date >= start,
            GSCPagesDaily.date <= end,
        )
        .group_by(GSCPagesDaily.page)
        .order_by(text("clicks DESC"))
    )

    buf, w = _writer()
    w.writerow(["page", "clicks", "impressions", "ctr", "position"])
    for r in result.all():
        clicks = float(r.clicks or 0)
        impressions = float(r.impressions or 0)
        ctr = _safe_div(clicks, impressions)
        position = _safe_div(float(r.weighted_position or 0), impressions)
        w.writerow([
            r.page,
            int(clicks),
            int(impressions),
            round(ctr, 6),
            round(position, 2),
        ])
    return buf.getvalue()
