from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime, timedelta
from typing import Any

from google.analytics.data_v1beta.types import DateRange, Dimension, Metric, RunReportRequest
from sqlalchemy.dialects.mysql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from prism.core.logging import logger
from prism.db.models.ga4 import (
    GA4ChannelsDaily,
    GA4DailyMetrics,
    GA4DevicesDaily,
    GA4EventsDaily,
    GA4GeoDaily,
    GA4HourlyMetrics,
    GA4LandingPageDeviceDaily,
    GA4LandingPagesDaily,
    GA4TrafficSourcesDaily,
    GA4UserTypeDaily,
)
from prism.db.models.sync import SyncJob
from prism.db.session import get_session_factory
from prism.services.ga4.client import get_ga4_client, run_report_with_backoff

_DEFAULT_BACKFILL_DAYS = 420   # 14 months
_DAILY_LOOKBACK_DAYS = 3      # catch GA4 reprocessing


def _int(val: str) -> int:
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return 0


def _float(val: str) -> float:
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0.0


def _parse_rows(response: Any, dim_names: list[str], metric_names: list[str]) -> list[dict]:
    rows = []
    for row in response.rows:
        record: dict[str, Any] = {}
        for i, dim in enumerate(dim_names):
            record[dim] = row.dimension_values[i].value
        for i, met in enumerate(metric_names):
            record[met] = row.metric_values[i].value
        rows.append(record)
    return rows


async def _upsert_daily_metrics(db: AsyncSession, property_id: int, rows: list[dict]) -> int:
    if not rows:
        return 0
    records = [
        {
            "property_id": property_id,
            "date": datetime.strptime(r["date"], "%Y%m%d").date(),
            "dimension_hash": "base",
            "dimensions": {},
            "sessions": _int(r.get("sessions", "0")),
            "users": _int(r.get("totalUsers", "0")),
            "new_users": _int(r.get("newUsers", "0")),
            "engaged_sessions": _int(r.get("engagedSessions", "0")),
            "engagement_rate": _float(r.get("engagementRate", "0")),
            "average_session_duration": _float(r.get("averageSessionDuration", "0")),
            "bounce_rate": _float(r.get("bounceRate", "0")),
            "screen_page_views": _int(r.get("screenPageViews", "0")),
            "conversions": _int(r.get("conversions", "0")),
            "total_revenue": _float(r.get("totalRevenue", "0")),
        }
        for r in rows
    ]
    stmt = insert(GA4DailyMetrics).values(records)
    stmt = stmt.on_duplicate_key_update(
        sessions=stmt.inserted.sessions,
        users=stmt.inserted.users,
        new_users=stmt.inserted.new_users,
        engaged_sessions=stmt.inserted.engaged_sessions,
        engagement_rate=stmt.inserted.engagement_rate,
        average_session_duration=stmt.inserted.average_session_duration,
        bounce_rate=stmt.inserted.bounce_rate,
        screen_page_views=stmt.inserted.screen_page_views,
        conversions=stmt.inserted.conversions,
        total_revenue=stmt.inserted.total_revenue,
    )
    await db.execute(stmt)
    return len(records)


async def _upsert_landing_pages(db: AsyncSession, property_id: int, rows: list[dict]) -> int:
    if not rows:
        return 0
    records = [
        {
            "property_id": property_id,
            "date": datetime.strptime(r["date"], "%Y%m%d").date(),
            "landing_page": r.get("landingPage", "(not set)")[:700],
            "sessions": _int(r.get("sessions", "0")),
            "users": _int(r.get("totalUsers", "0")),
            "conversions": _int(r.get("conversions", "0")),
            "revenue": _float(r.get("totalRevenue", "0")),
            "bounce_rate": _float(r.get("bounceRate", "0")),
            # screenPageViews ≈ exits + (page views minus exits). The closest
            # exit-rate signal in GA4's Data API is "screenPageViews × bounceRate"
            # but we want an absolute count. We approximate exits as
            # sessions × bounce_rate; GA4 doesn't expose a direct `exits` metric
            # but this stays consistent with how GSC/GA4 reporting tools think
            # of exits at the landing-page grain.
            "exits": int(round(
                _int(r.get("sessions", "0")) * _float(r.get("bounceRate", "0"))
            )),
        }
        for r in rows
    ]
    stmt = insert(GA4LandingPagesDaily).values(records)
    stmt = stmt.on_duplicate_key_update(
        sessions=stmt.inserted.sessions,
        users=stmt.inserted.users,
        conversions=stmt.inserted.conversions,
        revenue=stmt.inserted.revenue,
        bounce_rate=stmt.inserted.bounce_rate,
        exits=stmt.inserted.exits,
    )
    await db.execute(stmt)
    return len(records)


async def _upsert_landing_page_devices(
    db: AsyncSession, property_id: int, rows: list[dict],
) -> int:
    if not rows:
        return 0
    records = [
        {
            "property_id": property_id,
            "date": datetime.strptime(r["date"], "%Y%m%d").date(),
            "landing_page": (r.get("landingPage", "(not set)") or "(not set)")[:700],
            "device_category": (r.get("deviceCategory", "unknown") or "unknown")[:100],
            "sessions": _int(r.get("sessions", "0")),
            "users": _int(r.get("totalUsers", "0")),
            "engaged_sessions": _int(r.get("engagedSessions", "0")),
            "conversions": _int(r.get("conversions", "0")),
            "revenue": _float(r.get("totalRevenue", "0")),
            "bounce_rate": _float(r.get("bounceRate", "0")),
            "avg_session_duration": _float(r.get("averageSessionDuration", "0")),
            "exits": int(round(
                _int(r.get("sessions", "0")) * _float(r.get("bounceRate", "0"))
            )),
        }
        for r in rows
    ]
    stmt = insert(GA4LandingPageDeviceDaily).values(records)
    stmt = stmt.on_duplicate_key_update(
        sessions=stmt.inserted.sessions,
        users=stmt.inserted.users,
        engaged_sessions=stmt.inserted.engaged_sessions,
        conversions=stmt.inserted.conversions,
        revenue=stmt.inserted.revenue,
        bounce_rate=stmt.inserted.bounce_rate,
        avg_session_duration=stmt.inserted.avg_session_duration,
        exits=stmt.inserted.exits,
    )
    await db.execute(stmt)
    return len(records)


async def _upsert_traffic_sources(db: AsyncSession, property_id: int, rows: list[dict]) -> int:
    if not rows:
        return 0
    records = [
        {
            "property_id": property_id,
            "date": datetime.strptime(r["date"], "%Y%m%d").date(),
            "source": r.get("sessionSource", "(direct)")[:250],
            "medium": r.get("sessionMedium", "(none)")[:250],
            "campaign": r.get("sessionCampaignName", "(not set)")[:250],
            "sessions": _int(r.get("sessions", "0")),
            "users": _int(r.get("totalUsers", "0")),
            "conversions": _int(r.get("conversions", "0")),
        }
        for r in rows
    ]
    stmt = insert(GA4TrafficSourcesDaily).values(records)
    stmt = stmt.on_duplicate_key_update(
        sessions=stmt.inserted.sessions,
        users=stmt.inserted.users,
        conversions=stmt.inserted.conversions,
    )
    await db.execute(stmt)
    return len(records)


async def _upsert_devices(db: AsyncSession, property_id: int, rows: list[dict]) -> int:
    if not rows:
        return 0
    records = [
        {
            "property_id": property_id,
            "date": datetime.strptime(r["date"], "%Y%m%d").date(),
            "device_category": r.get("deviceCategory", "unknown")[:100],
            "sessions": _int(r.get("sessions", "0")),
            "users": _int(r.get("totalUsers", "0")),
            "conversions": _int(r.get("conversions", "0")),
        }
        for r in rows
    ]
    stmt = insert(GA4DevicesDaily).values(records)
    stmt = stmt.on_duplicate_key_update(
        sessions=stmt.inserted.sessions,
        users=stmt.inserted.users,
        conversions=stmt.inserted.conversions,
    )
    await db.execute(stmt)
    return len(records)


async def _upsert_geo(db: AsyncSession, property_id: int, rows: list[dict]) -> int:
    if not rows:
        return 0
    records = [
        {
            "property_id": property_id,
            "date": datetime.strptime(r["date"], "%Y%m%d").date(),
            "country": r.get("country", "(not set)")[:100],
            "region": r.get("region", "(not set)")[:200],
            "sessions": _int(r.get("sessions", "0")),
            "users": _int(r.get("totalUsers", "0")),
        }
        for r in rows
    ]
    stmt = insert(GA4GeoDaily).values(records)
    stmt = stmt.on_duplicate_key_update(
        sessions=stmt.inserted.sessions,
        users=stmt.inserted.users,
    )
    await db.execute(stmt)
    return len(records)


async def _upsert_events(db: AsyncSession, property_id: int, rows: list[dict]) -> int:
    if not rows:
        return 0
    records = [
        {
            "property_id": property_id,
            "date": datetime.strptime(r["date"], "%Y%m%d").date(),
            "event_name": r.get("eventName", "(not set)")[:500],
            "event_count": _int(r.get("eventCount", "0")),
            "conversions": _int(r.get("conversions", "0")),
        }
        for r in rows
    ]
    stmt = insert(GA4EventsDaily).values(records)
    stmt = stmt.on_duplicate_key_update(
        event_count=stmt.inserted.event_count,
        conversions=stmt.inserted.conversions,
    )
    await db.execute(stmt)
    return len(records)


def _date_range(start: date, end: date) -> DateRange:
    return DateRange(start_date=start.isoformat(), end_date=end.isoformat())


def _pull_report(
    client: Any,
    ga4_property_id: str,
    date_range: DateRange,
    dimensions: list[str],
    metrics: list[str],
    limit: int = 100_000,
) -> list[dict]:
    req = RunReportRequest(
        property=ga4_property_id,
        date_ranges=[date_range],
        dimensions=[Dimension(name=d) for d in dimensions],
        metrics=[Metric(name=m) for m in metrics],
        limit=limit,
    )
    response = run_report_with_backoff(client, req)
    return _parse_rows(response, dimensions, metrics)


async def ingest_property(
    property_id: int,
    ga4_property_id: str,
    start_date: date,
    end_date: date,
    refresh_token: str | None = None,
) -> int:
    """Pull all GA4 report shapes for the given date range and upsert into warehouse."""
    client = get_ga4_client(refresh_token)
    dr = _date_range(start_date, end_date)
    total_rows = 0

    def pull(dimensions: list[str], metrics: list[str], limit: int = 100_000) -> list[dict]:
        return _pull_report(client, ga4_property_id, dr, dimensions, metrics, limit)

    # Run all six report shapes — GA4 API calls are sync (blocking), so we offload to thread
    loop = asyncio.get_running_loop()

    daily_rows = await loop.run_in_executor(None, pull,
        ["date"],
        ["sessions", "totalUsers", "newUsers", "engagedSessions", "engagementRate",
         "averageSessionDuration", "bounceRate", "screenPageViews", "conversions", "totalRevenue"],
    )
    lp_rows = await loop.run_in_executor(None, pull,
        ["date", "landingPage"],
        ["sessions", "totalUsers", "conversions", "totalRevenue", "bounceRate"],
        50_000,
    )
    ts_rows = await loop.run_in_executor(None, pull,
        ["date", "sessionSource", "sessionMedium", "sessionCampaignName"],
        ["sessions", "totalUsers", "conversions"],
        50_000,
    )
    dev_rows = await loop.run_in_executor(None, pull,
        ["date", "deviceCategory"],
        ["sessions", "totalUsers", "conversions"],
    )
    geo_rows = await loop.run_in_executor(None, pull,
        ["date", "country", "region"],
        ["sessions", "totalUsers"],
        50_000,
    )
    ev_rows = await loop.run_in_executor(None, pull,
        ["date", "eventName"],
        ["eventCount", "conversions"],
    )
    ch_rows = await loop.run_in_executor(None, pull,
        ["date", "sessionDefaultChannelGroup"],
        ["sessions", "totalUsers", "conversions", "totalRevenue"],
    )
    hr_rows = await loop.run_in_executor(None, pull,
        ["date", "hour"],
        ["sessions", "totalUsers", "screenPageViews"],
    )
    ut_rows = await loop.run_in_executor(None, pull,
        ["date", "newVsReturning"],
        ["sessions", "totalUsers", "engagedSessions"],
    )
    lp_dev_rows = await loop.run_in_executor(None, pull,
        ["date", "landingPage", "deviceCategory"],
        ["sessions", "totalUsers", "engagedSessions", "conversions",
         "totalRevenue", "bounceRate", "averageSessionDuration"],
        50_000,
    )

    factory = get_session_factory()
    async with factory() as db:
        total_rows += await _upsert_daily_metrics(db, property_id, daily_rows)
        total_rows += await _upsert_landing_pages(db, property_id, lp_rows)
        total_rows += await _upsert_traffic_sources(db, property_id, ts_rows)
        total_rows += await _upsert_devices(db, property_id, dev_rows)
        total_rows += await _upsert_geo(db, property_id, geo_rows)
        total_rows += await _upsert_events(db, property_id, ev_rows)
        total_rows += await _upsert_channels(db, property_id, ch_rows)
        total_rows += await _upsert_hourly(db, property_id, hr_rows)
        total_rows += await _upsert_user_type(db, property_id, ut_rows)
        total_rows += await _upsert_landing_page_devices(db, property_id, lp_dev_rows)
        await db.commit()

    logger.info("GA4 ingestion complete", property_id=property_id, rows=total_rows,
                start=start_date.isoformat(), end=end_date.isoformat())
    return total_rows


async def run_daily_sync(property_id: int, ga4_property_id: str, refresh_token: str | None = None) -> int:
    end = date.today()
    start = end - timedelta(days=_DAILY_LOOKBACK_DAYS)
    return await ingest_property(property_id, ga4_property_id, start, end, refresh_token)


async def run_backfill(
    property_id: int,
    ga4_property_id: str,
    days: int = _DEFAULT_BACKFILL_DAYS,
    refresh_token: str | None = None,
) -> int:
    end = date.today()
    start = end - timedelta(days=days)
    return await ingest_property(property_id, ga4_property_id, start, end, refresh_token)


# ── Tier 1 dimension upserts ────────────────────────────────────────────────


async def _upsert_channels(db: AsyncSession, property_id: int, rows: list[dict]) -> int:
    if not rows:
        return 0
    records = [
        {
            "property_id": property_id,
            "date": datetime.strptime(r["date"], "%Y%m%d").date(),
            "channel_group": (r.get("sessionDefaultChannelGroup", "(Other)") or "(Other)")[:100],
            "sessions": _int(r.get("sessions", "0")),
            "users": _int(r.get("totalUsers", "0")),
            "conversions": _int(r.get("conversions", "0")),
            "total_revenue": _float(r.get("totalRevenue", "0")),
        }
        for r in rows
    ]
    stmt = insert(GA4ChannelsDaily).values(records)
    stmt = stmt.on_duplicate_key_update(
        sessions=stmt.inserted.sessions,
        users=stmt.inserted.users,
        conversions=stmt.inserted.conversions,
        total_revenue=stmt.inserted.total_revenue,
    )
    await db.execute(stmt)
    return len(records)


async def _upsert_hourly(db: AsyncSession, property_id: int, rows: list[dict]) -> int:
    if not rows:
        return 0
    records = [
        {
            "property_id": property_id,
            "date": datetime.strptime(r["date"], "%Y%m%d").date(),
            "hour": int(r.get("hour", "0") or "0"),
            "sessions": _int(r.get("sessions", "0")),
            "users": _int(r.get("totalUsers", "0")),
            "screen_page_views": _int(r.get("screenPageViews", "0")),
        }
        for r in rows
    ]
    stmt = insert(GA4HourlyMetrics).values(records)
    stmt = stmt.on_duplicate_key_update(
        sessions=stmt.inserted.sessions,
        users=stmt.inserted.users,
        screen_page_views=stmt.inserted.screen_page_views,
    )
    await db.execute(stmt)
    return len(records)


async def _upsert_user_type(db: AsyncSession, property_id: int, rows: list[dict]) -> int:
    if not rows:
        return 0
    records = [
        {
            "property_id": property_id,
            "date": datetime.strptime(r["date"], "%Y%m%d").date(),
            "user_type": (r.get("newVsReturning", "(not set)") or "(not set)")[:50],
            "sessions": _int(r.get("sessions", "0")),
            "users": _int(r.get("totalUsers", "0")),
            "engaged_sessions": _int(r.get("engagedSessions", "0")),
        }
        for r in rows
    ]
    stmt = insert(GA4UserTypeDaily).values(records)
    stmt = stmt.on_duplicate_key_update(
        sessions=stmt.inserted.sessions,
        users=stmt.inserted.users,
        engaged_sessions=stmt.inserted.engaged_sessions,
    )
    await db.execute(stmt)
    return len(records)
